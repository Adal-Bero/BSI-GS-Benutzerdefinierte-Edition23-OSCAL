import os
import sys
import json
import logging
import uuid
import asyncio
import random
from datetime import datetime, timezone

import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason, Tool, grounding
from google.cloud import storage
from google.api_core.exceptions import ResourceExhausted, InternalServerError, ServiceUnavailable, NotFound
from jsonschema import validate, ValidationError

# --- Configuration & Logging Setup ---
try:
    GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
    BUCKET_NAME = os.environ["BUCKET_NAME"]
    SOURCE_PREFIX = os.environ.get("SOURCE_PREFIX")
    EXISTING_JSON_GCS_PATH = os.environ.get("EXISTING_JSON_GCS_PATH")
    
    # B: Dynamically set logging level based on TEST_MODE
    TEST_MODE = os.environ.get("TEST", "false").lower() == 'true'
    LOG_LEVEL = logging.DEBUG if TEST_MODE else logging.INFO
    logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
    
# --- BEGIN: Suppress noisy third-party loggers ---
    # This block prevents verbose logs from underlying libraries like google.auth and urllib3,
    # which can spam the logs with unnecessary network-level details.
    noisy_loggers = [
        "google.auth",
        "google.api_core",
        "urllib3"
    ]

    # set these loggers to WARNING level
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    # --- END: Suppress noisy third-party loggers ---

    logging.info("Successfully loaded all required environment variables.")
except KeyError as e:
    logging.critical(f"FATAL: Missing required environment variable: {e}."); sys.exit(1)

# --- Internal Variables ---
FINAL_RESULT_PREFIX = "results/"
DISCOVERY_PROMPT_FILE = "prompt_discovery.txt"
GENERATION_PROMPT_FILE = "prompt_generation.txt"
OSCAL_SCHEMA_FILE = "bsi_gk_2023_oscal_schema.json"
DISCOVERY_STUB_SCHEMA_FILE = "discovery_stub_schema.json"
GENERATION_STUB_SCHEMA_FILE = "generation_stub_schema.json"

# --- Concurrency & Retry Config ---
CONCURRENT_REQUEST_LIMIT = 5
MAX_RETRIES = 5
generation_config = {"response_mime_type": "application/json", "max_output_tokens": 65536}

# --- Initialization ---
try:
    with open(DISCOVERY_PROMPT_FILE, 'r', encoding='utf-8') as f: discovery_prompt_text = f.read()
    with open(GENERATION_PROMPT_FILE, 'r', encoding='utf-8') as f: generation_prompt_template = f.read()
    with open(OSCAL_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_oscal_schema = json.load(f)
    with open(DISCOVERY_STUB_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_discovery_schema = json.load(f)
    with open(GENERATION_STUB_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_generation_schema = json.load(f)
    vertexai.init(project=GCP_PROJECT_ID, location="us-central1")
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    gemini_model = GenerativeModel("gemini-2.5-pro")
    # grounding_tool = Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
    
except Exception as e:
    logging.critical(f"FATAL: Failed to initialize: {e}", exc_info=True); sys.exit(1)


# --- Helper and Transformation Functions (Unchanged) ---
def clean_and_extract_json(raw_text: str) -> str | None:
    if not raw_text or not raw_text.strip(): return None
    start = raw_text.find('{'); end = raw_text.rfind('}')
    if start == -1 or end == -1 or end < start: return None
    return raw_text[start : end + 1]

def build_oscal_control(requirement_stub: dict, maturity_prose: dict) -> dict:
    oscal_parts = []
    levels = [("Partial", "partial", "1"), ("Foundational", "foundational", "2"), ("Defined", "defined", "3"), ("Enhanced", "enhanced", "4"), ("Comprehensive", "comprehensive", "5")]
    for title_suffix, class_suffix, level_num in levels:
        statement = maturity_prose.get(f"level_{level_num}_statement")
        if statement:
            oscal_parts.append({
                "id": f"{requirement_stub['id']}-m{level_num}", "name": "maturity-level-description",
                "title": f"Maturity Level {level_num}: {title_suffix}", "class": f"maturity-level-{class_suffix}",
                "parts": [
                    {"name": "statement", "prose": statement},
                    {"name": "guidance", "prose": maturity_prose.get(f"level_{level_num}_guidance", "")},
                    {"name": "assessment-method", "prose": maturity_prose.get(f"level_{level_num}_assessment", "")}]})
    return {"id": requirement_stub['id'], "title": requirement_stub['title'], "class": "technical", "props": [{"name": "level", "value": requirement_stub.get('props', {}).get('level', 'N/A'), "ns": "https://www.bsi.bund.de/ns/grundschutz"}, {"name": "phase", "value": requirement_stub.get('props', {}).get('phase', 'N/A'), "ns": "https://www.bsi.bund.de/ns/grundschutz"}], "parts": oscal_parts}

# --- Two-Stage Async Processing ---
async def process_baustein_pdf(blob, semaphore):
    """Orchestrates the two-stage generation process with retries for a single Baustein PDF."""
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                # STAGE 1: Discovery
                logging.debug(f"Stage 1: Discovering structure for {blob.name} (Attempt {attempt + 1}/{MAX_RETRIES})...")
                gcs_uri = f"gs://{BUCKET_NAME}/{blob.name}"
                file_part = Part.from_uri(gcs_uri, mime_type="application/pdf")
                response = await gemini_model.generate_content_async([file_part, discovery_prompt_text], generation_config=generation_config)
                
                if response.candidates[0].finish_reason == FinishReason.MAX_TOKENS:
                    raise ValueError("Discovery call was cut off by MAX_TOKENS limit.")
                if not response.text:
                    raise ValueError("Discovery call returned an empty response.")

                cleaned_discovery_json = clean_and_extract_json(response.text)
                if not cleaned_discovery_json: raise ValueError("Discovery call failed to produce valid JSON.")
                discovery_data = json.loads(cleaned_discovery_json)
                validate(instance=discovery_data, schema=loaded_discovery_schema)
                
                requirements_to_generate = discovery_data.get('requirements_list', [])
                logging.debug(f"Discovery successful. Found {len(requirements_to_generate)} requirements.")

                # A: Enhanced TEST_MODE logic to slice requirements data
                if TEST_MODE and requirements_to_generate:
                    total_reqs = len(requirements_to_generate)
                    slice_index = max(1, int(total_reqs * 0.10))
                    requirements_to_generate = requirements_to_generate[:slice_index]
                    logging.debug(f"TEST MODE: Sliced requirements to {len(requirements_to_generate)} of {total_reqs} (10%).")

                if not requirements_to_generate:
                    return discovery_data.get("main_group_id"), {"id": discovery_data.get("baustein_id"),"title": discovery_data.get("baustein_title"),"class": "baustein","parts": discovery_data.get("contextual_parts", []),"controls": []}

                # STAGE 2: Batch Generation
                logging.debug(f"Stage 2: Batch generating maturity prose for {len(requirements_to_generate)} requirements...")
                batch_prompt = generation_prompt_template.format(REQUIREMENTS_JSON_BATCH=json.dumps(requirements_to_generate, indent=2, ensure_ascii=False))
                
                response = await gemini_model.generate_content_async(
                #    batch_prompt, generation_config=generation_config, tools=[grounding_tool]
                    batch_prompt, generation_config=generation_config,
                )
                
                if response.candidates[0].finish_reason == FinishReason.MAX_TOKENS:
                    raise ValueError("Generation call was cut off by MAX_TOKENS limit.")
                if not response.text:
                    raise ValueError("Generation call returned an empty response.")

                cleaned_generation_json = clean_and_extract_json(response.text)
                if not cleaned_generation_json: raise ValueError("Generation call failed to produce valid JSON.")
                generation_data = json.loads(cleaned_generation_json)
                validate(instance=generation_data, schema=loaded_generation_schema)
                logging.debug(f"Batch generation successful.")
                
                # ASSEMBLY
                prose_map = {item['id']: item for item in generation_data.get('generated_requirements', [])}
                final_controls = [build_oscal_control(req_stub, prose_map[req_stub['id']]) for req_stub in requirements_to_generate if req_stub['id'] in prose_map]
                
                final_baustein_group = {
                    "id": discovery_data.get("baustein_id"), "title": discovery_data.get("baustein_title"),
                    "class": "baustein", "parts": discovery_data.get("contextual_parts", []), "controls": final_controls
                }
                return discovery_data.get("main_group_id"), final_baustein_group

            except Exception as e:
                logging.warning(f"Failed to process {blob.name} on attempt {attempt + 1}/{MAX_RETRIES}. Error: {e}")
                if attempt + 1 < MAX_RETRIES:
                    await asyncio.sleep((2 * (2 ** attempt)) + random.uniform(0, 1.0))
                else:
                    logging.error(f"All {MAX_RETRIES} attempts failed for {blob.name}. This Baustein will be skipped.", exc_info=True)
                    return None, None
        return None, None


# --- Main Execution and Catalog Management ---
def load_existing_catalog(bucket, gcs_path):
    if not gcs_path: logging.info("No existing JSON path provided. Starting with a fresh catalog."); return get_empty_catalog_structure()
    blob = bucket.blob(gcs_path)
    try:
        logging.info(f"Loading existing catalog from gs://{bucket.name}/{gcs_path}...")
        existing_catalog = json.loads(blob.download_as_string()); validate(instance=existing_catalog, schema=loaded_oscal_schema); return existing_catalog
    except NotFound: logging.warning(f"Existing catalog not found at gs://{bucket.name}/{gcs_path}. Creating new."); return get_empty_catalog_structure()
    except (json.JSONDecodeError, ValidationError) as e: logging.critical(f"FATAL: Existing JSON at {gcs_path} is invalid: {e}. Please fix."); sys.exit(1)
def get_empty_catalog_structure():
    groups = [{"id": "ISMS", "title": "ISMS: Sicherheitsmanagement"}, {"id": "ORP", "title": "ORP: Organisation und Personal"}, {"id": "CON", "title": "CON: Konzeption und Vorgehensweise"}, {"id": "OPS", "title": "OPS: Betrieb"}, {"id": "DER", "title": "DER: Detektion und Reaktion"}, {"id": "APP", "title": "APP: Anwendungen"}, {"id": "SYS", "title": "SYS: IT-Systeme"}, {"id": "IND", "title": "IND: Industrielle IT"}, {"id": "NET", "title": "NET: Netze und Kommunikation"}, {"id": "INF", "title": "INF: Infrastruktur"}]
    return {"catalog": {"uuid": str(uuid.uuid4()), "metadata": {"title": "Gesamtkatalog BSI Grundschutz Kompendium", "last-modified": datetime.now(timezone.utc).isoformat(), "version": "1.0.0", "oscal-version": "1.1.2"}, "groups": [{"id": g["id"], "class": "layer", "title": g["title"], "groups": []} for g in groups]}}
def merge_results(new_results, base_catalog):
    logging.debug("Starting merge process..."); main_groups_map = {g['id']: g for g in base_catalog['catalog']['groups']}
    for main_id, baustein in new_results:
        if not (main_id and baustein): continue
        b_id = baustein.get("id");
        if not b_id: logging.warning("Skipping result with no baustein 'id'."); continue
        if main_id in main_groups_map:
            target = main_groups_map[main_id]; idx = next((i for i, b in enumerate(target.get("groups", [])) if b.get("id") == b_id), -1)
            if idx != -1: logging.debug(f"Updating Baustein '{b_id}' in '{main_id}'."); target["groups"][idx] = baustein
            else: logging.debug(f"Adding new Baustein '{b_id}' to '{main_id}'."); target.setdefault("groups", []).append(baustein)
        else: logging.warning(f"Main Group ID '{main_id}' not in catalog. Skipping '{b_id}'.")
    for g in base_catalog['catalog']['groups']:
        if "groups" in g: g['groups'].sort(key=lambda x: x.get('id', ''))
    base_catalog["catalog"]["metadata"]["last-modified"] = datetime.now(timezone.utc).isoformat(); return base_catalog

async def main():
    logging.info(f"Job starting... [TEST_MODE={TEST_MODE}]")
    base_catalog = load_existing_catalog(bucket, EXISTING_JSON_GCS_PATH)
    
    all_blobs = list(storage_client.list_blobs(BUCKET_NAME, prefix=SOURCE_PREFIX))
    files_to_process = [blob for blob in all_blobs if blob.name.lower().endswith('.pdf')]
    if not files_to_process: logging.warning(f"No PDF files found in gs://{BUCKET_NAME}/{SOURCE_PREFIX}. Exiting."); return
    
    # A: Limit number of files in TEST_MODE
    if TEST_MODE: 
        files_to_process = files_to_process[:3]
        logging.warning(f"--- TEST MODE: Processing a maximum of {len(files_to_process)} files. ---")
    
    semaphore = asyncio.Semaphore(CONCURRENT_REQUEST_LIMIT)
    tasks = [process_baustein_pdf(blob, semaphore) for blob in files_to_process]
    
    all_results = await asyncio.gather(*tasks)
    successful_results = [res for res in all_results if res and res[0]]
    
    final_catalog = merge_results(successful_results, base_catalog)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_filename = f"{FINAL_RESULT_PREFIX}MERGED_BSI_Catalog_{timestamp}.json"
    output_blob = bucket.blob(output_filename)
    output_blob.upload_from_string(json.dumps(final_catalog, indent=2, ensure_ascii=False), "application/json")
    
    logging.info("--- Batch Job Summary ---")
    logging.info(f"Successfully processed: {len(successful_results)} file(s).")
    logging.info(f"Failed to process: {len(files_to_process) - len(successful_results)} file(s).")
    logging.info(f"Final merged catalog uploaded to: gs://{BUCKET_NAME}/{output_filename}")


if __name__ == "__main__":
    asyncio.run(main())