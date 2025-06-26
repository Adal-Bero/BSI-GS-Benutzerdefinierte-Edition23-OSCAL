import asyncio
import json
import logging
import os
import re
import sys
import textwrap
import time
import uuid
from typing import Any, Dict, List, Optional

import jsonschema
# MODIFIED: Switched to the google.generativeai library
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, GoogleSearch, Tool
from google.cloud import storage

# --- Configuration ---
class Config:
    """Loads and validates all configuration from environment variables."""
    def __init__(self):
        self.gcp_project_id: str = self._get_required_env("GCP_PROJECT_ID")
        self.bucket_name: str = self._get_required_env("BUCKET_NAME")
        self.source_prefix: str = self._get_required_env("SOURCE_PREFIX")
        self.output_prefix: str = self._get_required_env("OUTPUT_PREFIX")
        self.existing_json_gcs_path: str = self._get_required_env("EXISTING_JSON_GCS_PATH")
        self.test_mode: bool = os.getenv("TEST", "false").lower() == "true"
        
        self.output_filename = os.path.basename(self.existing_json_gcs_path)
        self.output_gcs_path = os.path.join(self.output_prefix, self.output_filename)

        logging.info("Configuration loaded successfully.")
        if self.test_mode:
            logging.warning("--- TEST MODE ENABLED ---")

    def _get_required_env(self, var_name: str) -> str:
        value = os.getenv(var_name)
        if not value:
            logging.error(f"FATAL: Environment variable '{var_name}' is not set.")
            sys.exit(1)
        return value

# --- Logging Setup ---
def setup_logging(test_mode: bool):
    """Configures the root logger based on the execution mode."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) 

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    
    if test_mode:
        handler.setLevel(logging.INFO) 
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    else:
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        logging.getLogger("google.auth").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("google.api_core").setLevel(logging.WARNING)
        # Also quiet the new library in production
        logging.getLogger("google.generativeai").setLevel(logging.WARNING)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    logging.info(f"Logging configured. Detailed logs: {'ON (INFO)' if test_mode else 'OFF (DEBUG)'}")


# --- Cloud Storage Utilities ---
def download_json_from_gcs(client: storage.Client, bucket_name: str, gcs_path: str) -> Optional[Dict]:
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        if not blob.exists():
            logging.error(f"GCS file not found: gs://{bucket_name}/{gcs_path}")
            return None
        json_data = json.loads(blob.download_as_string())
        logging.debug(f"Successfully downloaded JSON from gs://{bucket_name}/{gcs_path}")
        return json_data
    except Exception as e:
        logging.error(f"Failed to download or parse gs://{bucket_name}/{gcs_path}: {e}")
        return None

def upload_json_to_gcs(client: storage.Client, bucket_name: str, gcs_path: str, data: Dict):
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(json.dumps(data, indent=2, ensure_ascii=False), content_type='application/json')
        logging.info(f"Successfully uploaded JSON to gs://{bucket_name}/{gcs_path}")
    except Exception as e:
        logging.error(f"Failed to upload to gs://{bucket_name}/{gcs_path}: {e}")
        raise

def list_gcs_blobs(client: storage.Client, bucket_name: str, prefix: str) -> List[storage.Blob]:
    blobs = client.list_blobs(bucket_name, prefix=prefix)
    return [blob for blob in blobs if blob.name.endswith('.json')]


# --- OSCAL Catalog Utilities ---
def find_item_by_id_recursive(oscal_element: Any, target_id: str) -> Optional[Dict]:
    if isinstance(oscal_element, dict):
        if oscal_element.get("id") == target_id:
            return oscal_element
        for key, value in oscal_element.items():
            found = find_item_by_id_recursive(value, target_id)
            if found:
                return found
    elif isinstance(oscal_element, list):
        for item in oscal_element:
            found = find_item_by_id_recursive(item, target_id)
            if found:
                return found
    return None

def find_parent_baustein(element: Any, control_id: str) -> Optional[Dict]:
    if isinstance(element, dict):
        if element.get("class") == "baustein" and "controls" in element:
            control_ids_in_group = {c.get("id") for c in element.get("controls", [])}
            if control_id in control_ids_in_group:
                return element
        for value in element.values():
            found = find_parent_baustein(value, control_id)
            if found:
                return found
    elif isinstance(element, list):
        for item in element:
            found = find_parent_baustein(item, control_id)
            if found:
                return found
    return None

def get_prose_from_control(control: Dict) -> List[Dict[str, str]]:
    prose_parts = []
    if "parts" not in control:
        return []
    for ml_part in control.get("parts", []):
        if ml_part.get("name") == "maturity-level-description" and "parts" in ml_part:
            for content_part in ml_part.get("parts", []):
                if "prose" in content_part and "id" in content_part:
                    prose_parts.append({
                        "part_id": content_part["id"],
                        "prose": content_part["prose"]
                    })
    return prose_parts

def ensure_prose_part_ids(catalog: Dict):
    logging.info("Starting data sanitization: Ensuring all prose parts have IDs...")
    id_added_count = 0
    for top_group in catalog.get("catalog", {}).get("groups", []):
        for baustein in top_group.get("groups", []):
            if baustein.get("class") != "baustein":
                continue
            for control in baustein.get("controls", []):
                for ml_part in control.get("parts", []):
                    if ml_part.get("name") == "maturity-level-description" and "id" in ml_part and "parts" in ml_part:
                        for content_part in ml_part.get("parts", []):
                            if "prose" in content_part and "id" not in content_part and "name" in content_part:
                                content_part["id"] = f"{ml_part['id']}-{content_part['name']}"
                                id_added_count += 1
    logging.info(f"Data sanitization complete. Added {id_added_count} missing IDs to prose parts.")


# --- Gemini API Interaction (using google.generativeai) ---
def _clean_json_response(text: str) -> str:
    match = re.search(r"```(json)?\s*(\{.*})\s*```", text, re.DOTALL)
    if match:
        return match.group(2)
    return text

async def get_gemini_enrichment(model: genai.GenerativeModel, input_stub: Dict, prompt_template: str, output_schema: Dict) -> Optional[Dict]:
    full_prompt = textwrap.dedent(f"""
    {prompt_template}

    Here is the JSON object with the data to analyze:
    ```json
    {json.dumps(input_stub, indent=2, ensure_ascii=False)}
    ```

    Your response MUST be a single JSON object that validates against this schema:
    ```json
    {json.dumps(output_schema, indent=2)}
    ```
    """)
    
    generation_config = GenerationConfig(
        candidate_count=1,
        max_output_tokens=65536, 
        temperature=0.2, 
        response_mime_type="application/json"
    )
    
    # Correct tool initialization for google.genai
    tools = [Tool(google_search=GoogleSearch())]

    for attempt in range(5):
        try:
            logging.debug(f"Attempt {attempt + 1}/5 to call Gemini API for control {input_stub['control_context']['id']}.")
            # Correct API call for google.genai
            response = await model.generate_content_async(
                contents=full_prompt, 
                generation_config=generation_config, 
                tools=tools
            )
            
            # Response structure is similar enough to not require major changes here
            finish_reason = response.candidates[0].finish_reason.name
            if finish_reason not in ["STOP", "MAX_TOKENS"]: # google.genai uses MAX_TOKENS
                logging.warning(f"Gemini call for control {input_stub['control_context']['id']} finished with reason: {finish_reason}. Retrying...")
                await asyncio.sleep(2 ** attempt)
                continue

            response_text = _clean_json_response(response.text)
            model_output = json.loads(response_text)
            
            jsonschema.validate(instance=model_output, schema=output_schema)
            logging.debug(f"Successfully received and validated Gemini response for {input_stub['control_context']['id']}.")
            return model_output
        except Exception as e:
            logging.error(f"Error on attempt {attempt + 1} for control {input_stub['control_context']['id']}: {e}")
            if attempt < 4:
                await asyncio.sleep(2 ** attempt)
            else:
                logging.error(f"All 5 attempts failed for control {input_stub['control_context']['id']}. Skipping.")
                return None
    return None

# --- Main Processing Logic ---
async def process_control(control_id: str, source_catalog: Dict, model: genai.GenerativeModel, prompt_template: str, output_schema: Dict, semaphore: asyncio.Semaphore, catalog_lock: asyncio.Lock) -> List[Dict]:
    async with semaphore:
        logging.debug(f"Starting processing for control ID: {control_id}")
        
        control = find_item_by_id_recursive(source_catalog, control_id)
        baustein = find_parent_baustein(source_catalog.get("catalog"), control_id)

        if not control or not baustein:
            logging.warning(f"Could not find control '{control_id}' or its parent baustein in catalog. Skipping.")
            return []

        baustein_id = baustein.get("id")
        prose_to_evaluate = get_prose_from_control(control)
        if not prose_to_evaluate:
            logging.info(f"No prose with IDs found in control '{control_id}'. Skipping Gemini call.")
            return []

        input_stub = {
            "baustein_context": {"id": baustein["id"], "title": baustein["title"]},
            "control_context": {"id": control["id"], "title": control["title"]},
            "prose_to_evaluate": prose_to_evaluate,
        }

        gemini_result = await get_gemini_enrichment(model, input_stub, prompt_template, output_schema)

        if gemini_result:
            async with catalog_lock:
                target_baustein = find_parent_baustein(source_catalog.get("catalog"), control_id)
                if not target_baustein:
                    logging.error(f"FATAL: Baustein for {control_id} disappeared during lock. Concurrency issue?")
                    return []

                logging.debug(f"Acquired lock to merge results for {control_id}")
                for item in gemini_result.get("enriched_prose", []):
                    part = find_item_by_id_recursive(source_catalog, item["part_id"])
                    if part:
                        part["prose_qs"] = item["prose_qs"]
                
                new_controls = gemini_result.get("suggested_new_controls", [])
                if new_controls:
                    if "controls" not in target_baustein:
                        target_baustein["controls"] = []
                    for new_control in new_controls:
                        target_baustein["controls"].append(new_control)
                        logging.info(f"Added new suggested control '{new_control['id']}' to baustein '{baustein_id}' in main catalog.")
                logging.debug(f"Released lock for {control_id}")
            
            return gemini_result.get("suggested_new_controls", [])
        
        return []

async def main():
    """Main pipeline execution function."""
    config = Config()
    setup_logging(config.test_mode)

    try:
        # GCS client is unchanged
        storage_client = storage.Client(project=config.gcp_project_id)
        
        # MODIFIED: Initialize model using google.genai
        # ADC will be used automatically in a GCP environment.
        model = genai.GenerativeModel("gemini-2.5-pro")
    except Exception as e:
        logging.error(f"Failed to initialize clients: {e}")
        return

    logging.info("Loading prompts and schemas...")
    try:
        with open("prompts/quality_check_prompt.txt", "r") as f:
            prompt_template = f.read()
        with open("schemas/gemini_output_stub_schema.json", "r") as f:
            output_schema = json.load(f)
        with open("schemas/bsi_gk_2023_oscal_schema.json", "r") as f:
            final_oscal_schema = json.load(f)

    except FileNotFoundError as e:
        logging.error(f"Asset file not found: {e}. Exiting.")
        return

    logging.info(f"Loading source catalog from gs://{config.bucket_name}/{config.existing_json_gcs_path}")
    source_catalog = download_json_from_gcs(storage_client, config.bucket_name, config.existing_json_gcs_path)
    if not source_catalog:
        logging.error("Could not load source catalog. Exiting.")
        return

    ensure_prose_part_ids(source_catalog)

    logging.info(f"Discovering component files in gs://{config.bucket_name}/{config.source_prefix}...")
    component_blobs = list_gcs_blobs(storage_client, config.bucket_name, config.source_prefix)
    
    if config.test_mode:
        component_blobs = component_blobs[:3]
        logging.warning(f"TEST MODE: Processing only {len(component_blobs)} component files.")

    semaphore = asyncio.Semaphore(10)
    catalog_lock = asyncio.Lock()

    for blob in component_blobs:
        logging.info(f"--- Processing Component File: {blob.name} ---")
        component_data = download_json_from_gcs(storage_client, config.bucket_name, blob.name)
        if not component_data:
            continue
        component_tasks = []
        for component in component_data.get("component-definition", {}).get("components", []):
            for impl in component.get("control-implementations", []):
                control_ids = [req["control-id"] for req in impl.get("implemented-requirements", [])]
                if config.test_mode:
                    limit = max(1, int(len(control_ids) * 0.1))
                    control_ids = control_ids[:limit]
                    logging.warning(f"TEST MODE: Limiting to {len(control_ids)} controls for this component part.")
                for cid in control_ids:
                    task = asyncio.create_task(
                        process_control(
                            cid, source_catalog, model, prompt_template, 
                            output_schema, semaphore, catalog_lock
                        )
                    )
                    component_tasks.append(task)
        if not component_tasks:
            logging.info(f"No controls found to process in {blob.name}. Moving to next file.")
            continue
        list_of_new_controls_lists = await asyncio.gather(*component_tasks)
        aggregated_new_controls = [control for sublist in list_of_new_controls_lists for control in sublist]
        if aggregated_new_controls:
            logging.info(f"Found {len(aggregated_new_controls)} new controls to add to component {os.path.basename(blob.name)}.")
            try:
                first_control_impl = component_data["component-definition"]["components"][0]["control-implementations"][0]
                if "implemented-requirements" not in first_control_impl:
                    first_control_impl["implemented-requirements"] = []
                for new_control in aggregated_new_controls:
                    new_req = {
                        "uuid": str(uuid.uuid4()),
                        "control-id": new_control["id"],
                        "description": "AI-suggested control to address identified gap."
                    }
                    first_control_impl["implemented-requirements"].append(new_req)
                output_component_path = os.path.join(config.output_prefix, os.path.basename(blob.name))
                upload_json_to_gcs(storage_client, config.bucket_name, output_component_path, component_data)
            except (KeyError, IndexError) as e:
                logging.error(f"Could not add new controls to component {blob.name} due to unexpected structure: {e}")
        else:
            logging.info(f"No changes for component {blob.name}. Skipping save.")

    logging.info("All component processing complete. Starting final validation...")
    
    try:
        jsonschema.validate(instance=source_catalog, schema=final_oscal_schema)
        logging.info("Final catalog successfully validated against OSCAL schema.")
    except jsonschema.exceptions.ValidationError as e:
        logging.error(f"FATAL: Final assembled catalog is invalid and will not be uploaded. Reason: {e.message}")
        return

    upload_json_to_gcs(storage_client, config.bucket_name, config.output_gcs_path, source_catalog)
    logging.info("--- Pipeline Finished Successfully ---")

if __name__ == "__main__":
    asyncio.run(main())