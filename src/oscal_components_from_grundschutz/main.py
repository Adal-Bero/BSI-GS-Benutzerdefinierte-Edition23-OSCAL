import os
import json
import logging
import uuid
import sys
import time
import random
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from google.api_core import exceptions
import jsonschema

# --- Constants ---
TECHNICAL_MAIN_GROUPS = ["APP", "SYS", "IND", "NET", "INF"]
GENERIC_CONTROLS_FOR_STEP_6 = [
    "CON.1.A1", "CON.1.A4", "CON.3.A5", "DER.1.A5", "DER.1.A9",
    "OPS.1.1.2.A18", "OPS.1.1.2.A3", "OPS.1.1.2.A5", "OPS.1.1.2.A6",
    "OPS.1.1.3.A1", "OPS.1.2.5.A19", "ORP.1.A4", "ORP.2.A15",
    "ORP.4.A13", "ORP.4.A18", "ORP.4.A2", "ORP.4.A9"
]
# B. FIX: Define the list of keys to remove from schemas sent to the API
UNSUPPORTED_SCHEMA_KEYS = ["$schema", "$id", "title"]

# --- Configuration & Setup ---
class Config:
    """ Manages and validates all environment-based configuration. """
    def __init__(self):
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID")
        self.bucket_name = os.getenv("BUCKET_NAME")
        self.output_prefix = os.getenv("OUTPUT_PREFIX", "components")
        self.existing_json_gcs_path = os.getenv("EXISTING_JSON_GCS_PATH")
        self.is_test_mode = os.getenv("TEST", "false").lower() == "true"
        self.validate()

    def validate(self):
        required = {"GCP_PROJECT_ID": self.gcp_project_id, "BUCKET_NAME": self.bucket_name, "EXISTING_JSON_GCS_PATH": self.existing_json_gcs_path}
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

def setup_logging(is_test_mode: bool):
    """ Configures logging based on the execution mode. """
    level = logging.DEBUG if is_test_mode else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
    if not is_test_mode:
        for logger_name in ["google.auth", "google.api_core", "urllib3.connectionpool"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
    logging.info(f"Logging initialized. Test mode: {is_test_mode}")

# --- AI & GCS Interaction ---
def invoke_gemini(prompt: str, schema: Dict[str, Any], grounding: bool = False) -> Optional[Dict[str, Any]]:
    """ Invokes the Gemini model with retry logic, strict schema enforcement, and error handling. """
    # B. FIX: Sanitize the schema before sending it to the Vertex AI API
    sanitized_schema = {k: v for k, v in schema.items() if k not in UNSUPPORTED_SCHEMA_KEYS}

    model = GenerativeModel(
        "gemini-2.5-pro",
        generation_config=GenerationConfig(
            max_output_tokens=65536,
            response_mime_type="application/json",
            response_schema=sanitized_schema
        )
    )
    tools = [vertexai.generative_models.Tool.from_google_search_retrieval(grounding)] if grounding else None

    for attempt in range(5):
        try:
            logging.debug(f"Invoking Gemini (Attempt {attempt + 1}/5)...")
            response = model.generate_content(prompt, tools=tools)

            if response.candidates[0].finish_reason.name != "STOP":
                logging.warning(f"Gemini call finished with non-stop reason: {response.candidates[0].finish_reason.name}")
                continue

            parsed_json = json.loads(response.text)
            jsonschema.validate(instance=parsed_json, schema=schema) # Quality Gate (using original schema)
            logging.debug("Gemini response is valid and conforms to schema.")
            return parsed_json

        except Exception as e:
            logging.error(f"Error during Gemini invocation (Attempt {attempt + 1}): {e}", exc_info=True)
            if attempt < 4:
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                logging.info(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
    
    logging.critical("Failed to get a valid response from Gemini after 5 attempts.")
    return None

def download_json_from_gcs(client: storage.Client, bucket_name: str, blob_path: str) -> dict:
    full_path = f"gs://{bucket_name}/{blob_path}"
    logging.info(f"Downloading source catalog from {full_path}")
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return json.loads(blob.download_as_string())
    except Exception as e:
        logging.critical(f"Failed to download or parse {full_path}: {e}")
        raise

def upload_json_to_gcs(client: storage.Client, bucket_name: str, blob_path: str, data: dict):
    full_path = f"gs://{bucket_name}/{blob_path}"
    logging.info(f"Uploading component to {full_path}")
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
    except Exception as e:
        logging.error(f"Failed to upload to {full_path}: {e}")
        raise

# --- Catalog Helper Functions ---
def load_external_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

_catalog_cache = {}
def _find_group_by_id(groups: List[Dict[str, Any]], group_id: str) -> Optional[Dict[str, Any]]:
    if group_id in _catalog_cache: return _catalog_cache[group_id]
    for group in groups:
        if group.get("id") == group_id:
            _catalog_cache[group_id] = group
            return group
        if "groups" in group:
            found = _find_group_by_id(group["groups"], group_id)
            if found: return found
    return None

# A. FIX: New recursive helper function to find Bausteine by class
def _find_bausteine_recursive(groups: List[Dict[str, Any]], found_bausteine: List[Dict[str, Any]]):
    """ Recursively traverses groups to find all with class 'baustein'. """
    for group in groups:
        if group.get("class") == "baustein":
            found_bausteine.append(group)
        if "groups" in group:
            _find_bausteine_recursive(group["groups"], found_bausteine)

def find_target_bausteine(catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    """ Finds all Baustein-groups under the specified main technical groups. """
    target_bausteine = []
    # A. FIX: Use the new recursive search logic
    for main_group in catalog.get("catalog", {}).get("groups", []):
        if main_group.get("id") in TECHNICAL_MAIN_GROUPS:
            # Start the recursive search from within this main group
            _find_bausteine_recursive(main_group.get("groups", []), target_bausteine)
            
    logging.info(f"Found {len(target_bausteine)} target Bausteine to process.")
    return target_bausteine


def get_prose_from_part(parts_list: List[Dict[str, Any]], part_name: str) -> Optional[str]:
    for part in parts_list:
        if part.get("name") == part_name:
            return part.get("prose")
    return None

def expand_baustein_ids(catalog: Dict[str, Any], ids_to_expand: List[str]) -> List[str]:
    logging.debug(f"Expanding Baustein IDs (currently a passthrough): {ids_to_expand}")
    return list(set(ids_to_expand))

def get_controls_from_baustein_list(catalog: Dict[str, Any], baustein_ids: List[str]) -> List[Dict[str, Any]]:
    all_controls = []
    all_groups = catalog.get("catalog", {}).get("groups", [])
    for b_id in baustein_ids:
        group = _find_group_by_id(all_groups, b_id)
        if group and "controls" in group:
            all_controls.extend(group["controls"])
    logging.debug(f"Fetched {len(all_controls)} controls from {len(baustein_ids)} Bausteine.")
    return all_controls

# --- Component Manipulation Functions ---
def create_base_component(baustein_group: Dict[str, Any], source_url: str) -> Dict[str, Any]:
    component = {
        "component-definition": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": f"Component for Baustein {baustein_group.get('id')}: {baustein_group.get('title')}",
                "last-modified": datetime.now(timezone.utc).isoformat(),
                "version": "1.0.0",
                "oscal-version": "1.1.2",
                "remarks": f"AI-enriched component for {baustein_group.get('id')}."
            },
            "components": [{
                "uuid": str(uuid.uuid4()),
                "type": "service",
                "title": baustein_group.get('title'),
                "description": f"Implementation of controls for Baustein {baustein_group.get('id')}.",
                "control-implementations": []
            }]
        }
    }
    
    controls = baustein_group.get("controls", [])
    if controls:
        impl_reqs = [{"uuid": str(uuid.uuid4()), "control-id": c.get("id"), "description": f"Base implementation for control {c.get('id')}."} for c in controls]
        component["component-definition"]["components"][0]["control-implementations"].append({
            "uuid": str(uuid.uuid4()),
            "source": source_url,
            "description": f"Implementation for all controls in group {baustein_group.get('id')}: {baustein_group.get('title')}",
            "implemented-requirements": impl_reqs
        })
    return component

def add_controls_to_component(component: Dict[str, Any], controls_to_add: List[Dict[str, Any]], group_title: str, source_url: str):
    if not controls_to_add:
        return
    
    impl_reqs = [{"uuid": str(uuid.uuid4()), "control-id": c.get("id"), "description": f"Implementation for suggested control {c.get('id')}."} for c in controls_to_add]
    
    component["component-definition"]["components"][0]["control-implementations"].append({
        "uuid": str(uuid.uuid4()),
        "source": source_url,
        "description": group_title,
        "implemented-requirements": impl_reqs
    })
    logging.info(f"Added new implementation group '{group_title}' with {len(controls_to_add)} controls.")


# --- Main Processing Logic ---
def process_single_baustein(baustein_group: Dict[str, Any], catalog: Dict[str, Any], prompts: Dict[str, str], schemas: Dict[str, Any], source_url: str) -> Optional[Dict[str, Any]]:
    # (No changes in this function)
    baustein_id = baustein_group.get("id")
    logging.info(f"--- Starting processing for Baustein {baustein_id} ---")

    # C.1
    component = create_base_component(baustein_group, source_url)
    
    # C.2
    usage_prose = get_prose_from_part(baustein_group.get("parts", []), "usage")
    if not usage_prose:
        logging.warning(f"No 'usage' prose found for {baustein_id}. Skipping dependency extraction (C.2-C.5).")
        dependent_controls = []
    else:
        prompt = prompts["extract_dependencies"].format(schema=json.dumps(schemas["dependency"]), prose=usage_prose)
        dependency_result = invoke_gemini(prompt, schemas["dependency"])
        if not dependency_result: return None
        
        # C.3
        dependency_ids = expand_baustein_ids(catalog, dependency_result.get("dependencies", []))
        
        # C.4
        if not dependency_ids:
            logging.info("No dependencies found or extracted. Skipping control filtering (C.4).")
            dependent_controls = []
        else:
            candidate_controls = get_controls_from_baustein_list(catalog, dependency_ids)
            if not candidate_controls:
                logging.info(f"Dependencies {dependency_ids} have no controls. Skipping C.4.")
                dependent_controls = []
            else:
                context_prose = {
                    "introduction": get_prose_from_part(baustein_group.get("parts", []), "introduction"),
                    "objective": get_prose_from_part(baustein_group.get("parts", []), "objective"),
                    "usage": usage_prose
                }
                candidate_json = json.dumps([{"id": c.get("id"), "title": c.get("title")} for c in candidate_controls])
                prompt = prompts["filter_controls"].format(
                    schema=json.dumps(schemas["control_filter"]),
                    introduction_prose=context_prose["introduction"],
                    objective_prose=context_prose["objective"],
                    usage_prose=context_prose["usage"],
                    candidate_controls_json=candidate_json
                )
                filter_result = invoke_gemini(prompt, schemas["control_filter"])
                if not filter_result: return None
                
                approved_ids = filter_result.get("approved_controls", [])
                dependent_controls = [c for c in candidate_controls if c.get("id") in approved_ids]

    # C.5
    add_controls_to_component(component, dependent_controls, "Dependencies from related Bausteine", source_url)
    
    # C.6
    generic_candidate_controls = get_controls_from_baustein_list(catalog, GENERIC_CONTROLS_FOR_STEP_6)
    context_prose = {
        "introduction": get_prose_from_part(baustein_group.get("parts", []), "introduction"),
        "objective": get_prose_from_part(baustein_group.get("parts", []), "objective"),
        "usage": usage_prose or "N/A"
    }
    candidate_json = json.dumps([{"id": c.get("id"), "title": c.get("title")} for c in generic_candidate_controls])
    prompt = prompts["filter_controls"].format(
        schema=json.dumps(schemas["control_filter"]),
        introduction_prose=context_prose["introduction"],
        objective_prose=context_prose["objective"],
        usage_prose=context_prose["usage"],
        candidate_controls_json=candidate_json
    )
    generic_filter_result = invoke_gemini(prompt, schemas["control_filter"])
    if not generic_filter_result: return None

    approved_generic_ids = generic_filter_result.get("approved_controls", [])
    generic_controls_to_add = [c for c in generic_candidate_controls if c.get("id") in approved_generic_ids]
    
    # C.7
    add_controls_to_component(component, generic_controls_to_add, "SYS.0 Generic Controls", source_url)

    logging.info(f"--- Finished processing for Baustein {baustein_id} ---")
    return component


def main():
    # (No changes in this function)
    try:
        config = Config()
        setup_logging(config.is_test_mode)
    except ValueError as e:
        logging.critical(f"Configuration error: {e}")
        sys.exit(1)

    try:
        prompts = {
            "extract_dependencies": load_external_file("prompts/extract_dependencies_prompt.txt"),
            "filter_controls": load_external_file("prompts/filter_controls_prompt.txt")
        }
        schemas = {
            "dependency": json.loads(load_external_file("schemas/dependency_schema.json")),
            "control_filter": json.loads(load_external_file("schemas/control_filter_schema.json")),
            "oscal_component": json.loads(load_external_file("schemas/oscal_component_schema.json"))
        }

        storage_client = storage.Client(project=config.gcp_project_id)
        vertexai.init(project=config.gcp_project_id, location="us-central1")

        catalog = download_json_from_gcs(storage_client, config.bucket_name, config.existing_json_gcs_path)
        source_url = f"gs://{config.bucket_name}/{config.existing_json_gcs_path}"
        
        target_bausteine = find_target_bausteine(catalog)
        
        if config.is_test_mode:
            logging.warning(f"TEST MODE: Processing only the first 3 of {len(target_bausteine)} Bausteine.")
            target_bausteine = target_bausteine[:3]
        
        for baustein in target_bausteine:
            baustein_id = baustein.get("id")
            try:
                final_component = process_single_baustein(baustein, catalog, prompts, schemas, source_url)
                if final_component:
                    jsonschema.validate(instance=final_component, schema=schemas["oscal_component"])
                    output_path = os.path.join(config.output_prefix, f"{baustein_id}.component.json")
                    upload_json_to_gcs(storage_client, config.bucket_name, output_path, final_component)
            except Exception as e:
                logging.error(f"FATAL ERROR while processing Baustein {baustein_id}. Skipping. Error: {e}", exc_info=True)

        logging.info("Job completed.")

    except Exception as e:
        logging.critical(f"A critical, unrecoverable error occurred in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()