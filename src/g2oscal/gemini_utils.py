import asyncio
import json
import logging
import random

import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
from jsonschema import validate

from config import (GCP_PROJECT_ID, MAX_RETRIES, TEST_MODE, BUCKET_NAME,
                    DISCOVERY_PROMPT_FILE, GENERATION_PROMPT_FILE, ENRICHMENT_PROMPT_FILE,
                    DISCOVERY_STUB_SCHEMA_FILE, GENERATION_STUB_SCHEMA_FILE, ENRICHMENT_STUB_SCHEMA_FILE)

logger = logging.getLogger(__name__)

# --- Initialization ---
try:
    with open(DISCOVERY_PROMPT_FILE, 'r', encoding='utf-8') as f: discovery_prompt_text = f.read()
    with open(GENERATION_PROMPT_FILE, 'r', encoding='utf-8') as f: generation_prompt_template = f.read()
    with open(ENRICHMENT_PROMPT_FILE, 'r', encoding='utf-8') as f: enrichment_prompt_template = f.read()
    with open(DISCOVERY_STUB_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_discovery_schema = json.load(f)
    with open(GENERATION_STUB_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_generation_schema = json.load(f)
    with open(ENRICHMENT_STUB_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_enrichment_schema = json.load(f)
    
    vertexai.init(project=GCP_PROJECT_ID, location="us-central1")
    gemini_model = GenerativeModel("gemini-2.5-pro")
    generation_config = {"response_mime_type": "application/json", "max_output_tokens": 65536}

except Exception as e:
    logging.critical(f"FATAL: Failed to initialize Gemini Utils: {e}", exc_info=True)
    raise

# --- Helper Functions ---
def clean_and_extract_json(raw_text: str) -> str | None:
    if not raw_text or not raw_text.strip(): return None
    start = raw_text.find('{'); end = raw_text.rfind('}')
    if start == -1 or end == -1 or end < start: return None
    return raw_text[start : end + 1]

async def call_gemini_api(prompt, schema_to_validate):
    """Generic function to call Gemini and validate the response."""
    if not isinstance(prompt, list):
        prompt = [prompt]
        
    response = await gemini_model.generate_content_async(prompt, generation_config=generation_config)
    
    if not response.candidates or response.candidates[0].finish_reason != FinishReason.STOP:
        reason = "Unknown"
        if response.candidates:
            reason = response.candidates[0].finish_reason.name
        raise ValueError(f"API call failed or was blocked. Reason: {reason}")

    cleaned_json_text = clean_and_extract_json(response.text)
    if not cleaned_json_text:
        raise ValueError("Failed to produce valid JSON from response.")
        
    data = json.loads(cleaned_json_text)
    validate(instance=data, schema=schema_to_validate)
    return data

# --- Main Processing Logic ---
async def process_baustein_pdf(blob, semaphore, build_oscal_control_func):
    """Orchestrates the multi-stage generation process for a single Baustein PDF."""
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                # STAGE 1: Discovery
                logging.debug(f"Stage 1: Discovering structure for {blob.name} (Attempt {attempt + 1}/{MAX_RETRIES})...")
                gcs_uri = f"gs://{BUCKET_NAME}/{blob.name}"
                file_part = Part.from_uri(gcs_uri, mime_type="application/pdf")
                discovery_data = await call_gemini_api([file_part, discovery_prompt_text], loaded_discovery_schema)
                
                requirements_to_process = discovery_data.get('requirements_list', [])
                logging.debug(f"Discovery successful. Found {len(requirements_to_process)} requirements.")

                if TEST_MODE and requirements_to_process:
                    slice_index = max(1, int(len(requirements_to_process) * 0.10))
                    requirements_to_process = requirements_to_process[:slice_index]
                    logging.debug(f"TEST MODE: Sliced requirements to {len(requirements_to_process)}.")

                if not requirements_to_process:
                    return discovery_data.get("main_group_id"), {"id": discovery_data.get("baustein_id"),"title": discovery_data.get("baustein_title"),"class": "baustein","parts": discovery_data.get("contextual_parts", []),"controls": []}

                # STAGE 2 & 3: Parallel Generation and Enrichment
                logging.debug(f"Stages 2&3: Starting parallel tasks for {len(requirements_to_process)} requirements...")
                
                generation_batch_prompt = generation_prompt_template.format(REQUIREMENTS_JSON_BATCH=json.dumps(requirements_to_process, indent=2, ensure_ascii=False))
                enrichment_batch_prompt = enrichment_prompt_template.format(REQUIREMENTS_JSON_BATCH=json.dumps(requirements_to_process, indent=2, ensure_ascii=False))

                generation_task = call_gemini_api(generation_batch_prompt, loaded_generation_schema)
                enrichment_task = call_gemini_api(enrichment_batch_prompt, loaded_enrichment_schema)
                
                generation_data, enrichment_data = await asyncio.gather(generation_task, enrichment_task)
                
                logging.debug(f"Parallel generation and enrichment successful.")
                
                # ASSEMBLY
                prose_map = {item['id']: item for item in generation_data.get('generated_requirements', [])}
                enrichment_map = {item['id']: item for item in enrichment_data.get('enriched_requirements', [])}
                
                final_controls = [build_oscal_control_func(req_stub, prose_map[req_stub['id']], enrichment_map[req_stub['id']]) 
                                  for req_stub in requirements_to_process if req_stub['id'] in prose_map and req_stub['id'] in enrichment_map]
                
                final_baustein_group = {
                    "id": discovery_data.get("baustein_id"), "title": discovery_data.get("baustein_title"),
                    "class": "baustein", "parts": discovery_data.get("contextual_parts", []), "controls": final_controls
                }
                return discovery_data.get("main_group_id"), final_baustein_group

            except Exception as e:
                logging.warning(f"Failed to process {blob.name} on attempt {attempt + 1}/{MAX_RETRIES}. Error: {e}")
                if attempt + 1 < MAX_RETRIES:
                    await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
                else:
                    logging.error(f"All {MAX_RETRIES} attempts failed for {blob.name}. This Baustein will be skipped.", exc_info=TEST_MODE)
                    return None, None
        return None, None