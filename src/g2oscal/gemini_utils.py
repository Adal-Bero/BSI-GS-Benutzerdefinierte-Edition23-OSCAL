import asyncio
import json
import logging
import random

import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
from jsonschema import validate

from config import (GCP_PROJECT_ID, MAX_RETRIES, TEST_MODE, BUCKET_NAME,
                    DISCOVERY_ENRICHMENT_PROMPT_FILE, GENERATION_PROMPT_FILE,
                    DISCOVERY_ENRICHMENT_STUB_SCHEMA_FILE, GENERATION_STUB_SCHEMA_FILE)

logger = logging.getLogger(__name__)

# --- Initialization ---
try:
    with open(DISCOVERY_ENRICHMENT_PROMPT_FILE, 'r', encoding='utf-8') as f: discovery_enrichment_prompt_text = f.read()
    with open(GENERATION_PROMPT_FILE, 'r', encoding='utf-8') as f: generation_prompt_template = f.read()
    with open(DISCOVERY_ENRICHMENT_STUB_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_discovery_enrichment_schema = json.load(f)
    with open(GENERATION_STUB_SCHEMA_FILE, 'r', encoding='utf-8') as f: loaded_generation_schema = json.load(f)
    
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

# REWRITTEN: This function now contains its own robust retry loop.
async def call_gemini_api(prompt, schema_to_validate):
    """Generic function to call Gemini with retries and validate the response."""
    if not isinstance(prompt, list):
        prompt = [prompt]
    
    for attempt in range(MAX_RETRIES):
        try:
            response = await gemini_model.generate_content_async(prompt, generation_config=generation_config)
            
            if not response.candidates or response.candidates[0].finish_reason != FinishReason.STOP:
                reason = "Unknown"
                if response.candidates: reason = response.candidates[0].finish_reason.name
                raise ValueError(f"API call failed or was blocked. Reason: {reason}")

            cleaned_json_text = clean_and_extract_json(response.text)
            if not cleaned_json_text:
                raise ValueError("Failed to produce valid JSON from response.")
                
            data = json.loads(cleaned_json_text)
            validate(instance=data, schema=schema_to_validate)
            return data # Success
            
        except Exception as e:
            logging.warning(f"Gemini API call attempt {attempt + 1}/{MAX_RETRIES} failed. Error: {e}")
            if attempt + 1 == MAX_RETRIES:
                raise  # Re-raise the final exception
            await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))

# --- Main Processing Logic ---
async def process_baustein_pdf(blob, semaphore, build_oscal_control_func):
    """Orchestrates the new two-stage generation process for a single Baustein PDF."""
    async with semaphore:
        try:
            # STAGE 1: Combined Discovery & Enrichment
            logging.debug(f"Stage 1: Discovering & Enriching structure for {blob.name}...")
            gcs_uri = f"gs://{BUCKET_NAME}/{blob.name}"
            file_part = Part.from_uri(gcs_uri, mime_type="application/pdf")
            discovery_enrichment_data = await call_gemini_api([file_part, discovery_enrichment_prompt_text], loaded_discovery_enrichment_schema)
            
            requirements_to_process = discovery_enrichment_data.get('requirements_list', [])
            logging.debug(f"Discovery & Enrichment successful. Found {len(requirements_to_process)} requirements.")

            if TEST_MODE and requirements_to_process:
                slice_index = max(1, int(len(requirements_to_process) * 0.10))
                requirements_to_process = requirements_to_process[:slice_index]
                logging.debug(f"TEST MODE: Sliced requirements to {len(requirements_to_process)}.")

            if not requirements_to_process:
                return discovery_enrichment_data.get("main_group_id"), {"id": discovery_enrichment_data.get("baustein_id"),"title": discovery_enrichment_data.get("baustein_title"),"class": "baustein","parts": discovery_enrichment_data.get("contextual_parts", []),"controls": []}

            # STAGE 2: Generation of Maturity Prose
            logging.debug(f"Stage 2: Generating maturity prose for {len(requirements_to_process)} requirements...")
            generation_batch_prompt = generation_prompt_template.format(REQUIREMENTS_JSON_BATCH=json.dumps(requirements_to_process, indent=2, ensure_ascii=False))
            generation_data = await call_gemini_api(generation_batch_prompt, loaded_generation_schema)
            logging.debug(f"Maturity prose generation successful.")
            
            # ASSEMBLY
            prose_map = {item['id']: item for item in generation_data.get('generated_requirements', [])}
            
            final_controls = []
            for req_stub in requirements_to_process:
                req_id = req_stub['id']
                if req_id in prose_map:
                    # The stub itself now contains the enrichment data (class, practice, etc.)
                    final_controls.append(build_oscal_control_func(req_stub, prose_map[req_id]))
                else:
                    logging.warning(f"Skipping control '{req_id}' due to missing data in Generation stage.")
            
            final_baustein_group = {
                "id": discovery_enrichment_data.get("baustein_id"), "title": discovery_enrichment_data.get("baustein_title"),
                "class": "baustein", "parts": discovery_enrichment_data.get("contextual_parts", []), "controls": final_controls
            }
            return discovery_enrichment_data.get("main_group_id"), final_baustein_group

        except Exception as e:
            logging.error(f"Processing failed permanently for {blob.name} after all retries. Error: {e}", exc_info=TEST_MODE)
            return None, None