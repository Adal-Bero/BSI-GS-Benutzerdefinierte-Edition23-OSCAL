import asyncio
import json
import logging
import os
import re
import sys
import textwrap
import time
from typing import Any, Dict, List, Optional, Tuple

import jsonschema
import vertexai
from google.cloud import storage
from vertexai.generative_models import (GenerationConfig, GenerativeModel,
                                        Tool)

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
        
        # Derived paths
        self.output_filename = os.path.basename(self.existing_json_gcs_path)
        self.output_gcs_path = os.path.join(self.output_prefix, self.output_filename)

        logging.info("Configuration loaded successfully.")
        if self.test_mode:
            logging.warning("--- TEST MODE ENABLED ---")

    def _get_required_env(self, var_name: str) -> str:
        """Gets a required environment variable or exits."""
        value = os.getenv(var_name)
        if not value:
            logging.error(f"FATAL: Environment variable '{var_name}' is not set.")
            sys.exit(1)
        return value

# --- Logging Setup ---

def setup_logging(test_mode: bool):
    """Configures the root logger based on the execution mode."""
    log_level = logging.INFO if test_mode else logging.DEBUG
    root_logger = logging.getLogger()
    
    # Set the root logger's level; handlers will filter from this
    root_logger.setLevel(logging.DEBUG) 

    # Clear existing handlers
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    
    # In test mode, we want all DEBUG/INFO. In prod, we want high-level INFO.
    if test_mode:
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    else:
        handler.setLevel(logging.INFO) # Handler is INFO to show high-level status
        # In prod, step-by-step messages are logged at DEBUG, so they won't pass the INFO handler.
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Suppress verbose logs from third-party libraries in production
        logging.getLogger("google.auth").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("google.api_core").setLevel(logging.WARNING)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    logging.info(f"Logging configured. Detailed logs: {'ON (INFO)' if test_mode else 'OFF (DEBUG)'}")


# --- Cloud Storage Utilities ---

def download_json_from_gcs(client: storage.Client, bucket_name: str, gcs_path: str) -> Optional[Dict]:
    """Downloads and parses a JSON file from GCS."""
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
    """Uploads a dictionary as a JSON file to GCS."""
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(json.dumps(data, indent=2, ensure_ascii=False), content_type='application/json')
        logging.info(f"Successfully uploaded JSON to gs://{bucket_name}/{gcs_path}")
    except Exception as e:
        logging.error(f"Failed to upload to gs://{bucket_name}/{gcs_path}: {e}")
        raise

def list_gcs_blobs(client: storage.Client, bucket_name: str, prefix: str) -> List[storage.Blob]:
    """Lists all blobs in a GCS prefix."""
    blobs = client.list_blobs(bucket_name, prefix=prefix)
    return [blob for blob in blobs if blob.name.endswith('.json')]

# --- OSCAL Catalog Utilities ---

def find_item_by_id_recursive(oscal_element: Any, target_id: str) -> Optional[Dict]:
    """Recursively searches for a group, control, or part by its 'id'."""
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

def get_prose_from_control(control: Dict) -> List[Dict[str, str]]:
    """Extracts all prose parts from a control's maturity levels."""
    prose_parts = []
    if "parts" not in control:
        return []
    # Maturity levels are parts with name 'maturity-level-description'
    for ml_part in control.get("parts", []):
        if ml_part.get("name") == "maturity-level-description" and "parts" in ml_part:
            # The actual content parts (statement, guidance, etc.) are nested
            for content_part in ml_part.get("parts", []):
                if "prose" in content_part and "id" in content_part:
                    prose_parts.append({
                        "part_id": content_part["id"],
                        "prose": content_part["prose"]
                    })
    return prose_parts

# --- Gemini API Interaction ---

def _clean_json_response(text: str) -> str:
    """Cleans the model's response to extract the JSON object."""
    match = re.search(r"```(json)?\s*(\{.*})\s*```", text, re.DOTALL)
    if match:
        return match.group(2)
    return text # Assume it's already a valid JSON string

async def get_gemini_enrichment(
    model: GenerativeModel,
    input_stub: Dict,
    prompt_template: str,
    output_schema: Dict
) -> Optional[Dict]:
    """
    Calls the Gemini API with retry logic, grounding, and JSON validation.
    
    Args:
        model: The initialized GenerativeModel instance.
        input_stub: The JSON data to send to the model.
        prompt_template: The prompt text.
        output_schema: The JSON schema to validate the output against.

    Returns:
        A dictionary with the validated model output, or None on failure.
    """
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
        max_output_tokens=65536,
        temperature=0.2,
        response_mime_type="application/json"
    )
    
    # Enable grounding with Google Search
    tools = [Tool.from_google_search_retrieval()]

    for attempt in range(5):
        try:
            logging.debug(f"Attempt {attempt + 1}/5 to call Gemini API for control {input_stub['control_context']['id']}.")
            response = await model.generate_content_async(
                full_prompt,
                generation_config=generation_config,
                tools=tools,
            )

            finish_reason = response.candidates[0].finish_reason.name
            if finish_reason not in ["STOP", "NORMAL"]:
                logging.warning(
                    f"Gemini call for control {input_stub['control_context']['id']} "
                    f"finished with reason: {finish_reason}. Retrying..."
                )
                await asyncio.sleep(2 ** attempt)
                continue

            response_text = _clean_json_response(response.text)
            model_output = json.loads(response_text)
            
            # Schema as Quality Gate
            jsonschema.validate(instance=model_output, schema=output_schema)
            
            logging.debug(f"Successfully received and validated Gemini response for {input_stub['control_context']['id']}.")
            return model_output

        except Exception as e:
            logging.error(
                f"Error on attempt {attempt + 1} for control {input_stub['control_context']['id']}: {e}"
            )
            if attempt < 4:
                await asyncio.sleep(2 ** attempt)
            else:
                logging.error(f"All 5 attempts failed for control {input_stub['control_context']['id']}. Skipping.")
                return None
    return None

# --- Main Processing Logic ---

async def process_control(
    control_id: str,
    baustein_id: str,
    source_catalog: Dict,
    model: GenerativeModel,
    prompt_template: str,
    output_schema: Dict,
    semaphore: asyncio.Semaphore,
    catalog_lock: asyncio.Lock
) -> None:
    """
    Processes a single control: finds it, prepares data, calls Gemini, and merges results.
    """
    async with semaphore:
        logging.debug(f"Starting processing for control ID: {control_id}")
        
        control = find_item_by_id_recursive(source_catalog, control_id)
        baustein = find_item_by_id_recursive(source_catalog, baustein_id)

        if not control or not baustein:
            logging.warning(f"Could not find control '{control_id}' or baustein '{baustein_id}' in catalog. Skipping.")
            return

        prose_to_evaluate = get_prose_from_control(control)
        if not prose_to_evaluate:
            logging.info(f"No prose with IDs found in control '{control_id}'. Skipping Gemini call.")
            return

        input_stub = {
            "baustein_context": {"id": baustein["id"], "title": baustein["title"]},
            "control_context": {"id": control["id"], "title": control["title"]},
            "prose_to_evaluate": prose_to_evaluate,
        }

        gemini_result = await get_gemini_enrichment(model, input_stub, prompt_template, output_schema)

        if gemini_result:
            # Use a lock to prevent race conditions when modifying the shared catalog
            async with catalog_lock:
                logging.debug(f"Acquired lock to merge results for {control_id}")
                # 1. Merge enriched prose
                for item in gemini_result.get("enriched_prose", []):
                    part = find_item_by_id_recursive(source_catalog, item["part_id"])
                    if part:
                        part["prose_qs"] = item["prose_qs"]
                        logging.debug(f"Added 'prose_qs' to part {item['part_id']}")
                    else:
                        logging.warning(f"Could not find part {item['part_id']} to merge 'prose_qs'")
                
                # 2. Add suggested new controls
                if "suggested_new_controls" in gemini_result and gemini_result["suggested_new_controls"]:
                    # Find the baustein again within the locked context to ensure we modify the right object
                    target_baustein = find_item_by_id_recursive(source_catalog, baustein_id)
                    if target_baustein:
                        if "controls" not in target_baustein:
                            target_baustein["controls"] = []
                        for new_control in gemini_result["suggested_new_controls"]:
                            target_baustein["controls"].append(new_control)
                            logging.info(f"Added new suggested control '{new_control['id']}' to baustein '{baustein_id}'")
                logging.debug(f"Released lock for {control_id}")


async def main():
    """Main pipeline execution function."""
    config = Config()
    setup_logging(config.test_mode)

    # Initialize clients
    try:
        vertexai.init(project=config.gcp_project_id)
        storage_client = storage.Client(project=config.gcp_project_id)
        model = GenerativeModel("gemini-1.5-pro-001") # Using the model from the stable brief
    except Exception as e:
        logging.error(f"Failed to initialize GCP clients: {e}")
        return

    # Load external assets
    logging.info("Loading prompts and schemas...")
    try:
        with open("prompts/quality_check_prompt.txt", "r") as f:
            prompt_template = f.read()
        with open("schemas/gemini_output_stub_schema.json", "r") as f:
            output_schema = json.load(f)
    except FileNotFoundError as e:
        logging.error(f"Asset file not found: {e}. Exiting.")
        return

    # Load the main source catalog
    logging.info(f"Loading source catalog from gs://{config.bucket_name}/{config.existing_json_gcs_path}")
    source_catalog = download_json_from_gcs(storage_client, config.bucket_name, config.existing_json_gcs_path)
    if not source_catalog:
        logging.error("Could not load source catalog. Exiting.")
        return

    # Discover component files
    logging.info(f"Discovering component files in gs://{config.bucket_name}/{config.source_prefix}...")
    component_blobs = list_gcs_blobs(storage_client, config.bucket_name, config.source_prefix)
    
    if config.test_mode:
        component_blobs = component_blobs[:3]
        logging.warning(f"TEST MODE: Processing only {len(component_blobs)} component files.")

    # Collect all tasks
    tasks = []
    semaphore = asyncio.Semaphore(10) # Limit concurrent API calls
    catalog_lock = asyncio.Lock() # Lock for safe mutation of the shared catalog

    for blob in component_blobs:
        logging.info(f"Processing component file: {blob.name}")
        component_data = download_json_from_gcs(storage_client, config.bucket_name, blob.name)
        if not component_data:
            continue
        
        # This structure assumes the component definition schema provided
        for component in component_data.get("component-definition", {}).get("components", []):
            baustein_id = component.get("title", "").split(":")[0].strip().replace(".","_") # Heuristic to get Baustein ID
            for impl in component.get("control-implementations", []):
                control_ids = [req["control-id"] for req in impl.get("implemented-requirements", [])]
                
                if config.test_mode:
                    limit = max(1, int(len(control_ids) * 0.1))
                    control_ids = control_ids[:limit]
                    logging.warning(f"TEST MODE: Limiting to {len(control_ids)} controls for this component part.")

                for cid in control_ids:
                    task = asyncio.create_task(
                        process_control(cid, baustein_id, source_catalog, model, prompt_template, output_schema, semaphore, catalog_lock)
                    )
                    tasks.append(task)
    
    if not tasks:
        logging.warning("No controls found to process across all component files.")
        return

    # Run all tasks concurrently
    logging.info(f"Starting processing for {len(tasks)} total controls...")
    await asyncio.gather(*tasks)

    # Final step: upload the modified catalog
    logging.info("All processing complete. Uploading final catalog...")
    upload_json_to_gcs(storage_client, config.bucket_name, config.output_gcs_path, source_catalog)
    logging.info("--- Pipeline Finished Successfully ---")


if __name__ == "__main__":
    asyncio.run(main())