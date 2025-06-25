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
UNSUPPORTED_SCHEMA_KEYS = ["$schema", "$id", "title"]

# --- Configuration & Setup ---
class Config:
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
        if missing: raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

def setup_logging(is_test_mode: bool):
    level = logging.DEBUG if is_test_mode else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
    if not is_test_mode:
        for logger_name in ["google.auth", "google.api_core", "urllib3.connectionpool"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
    logging.info(f"Logging initialized. Test mode: {is_test_mode}")

# --- AI & GCS Interaction ---
def invoke_gemini(prompt: str, schema: Dict[str, Any], grounding: bool = False) -> Optional[Dict[str, Any]]:
    sanitized_schema = {k: v for k, v in schema.items() if k not in UNSUPPORTED_SCHEMA_KEYS}
    model = GenerativeModel("gemini-2.5-pro", generation_config=GenerationConfig(max_output_tokens=65536, response_mime_type="application/json", response_schema=sanitized_schema))
    tools = [vertexai.generative_models.Tool.from_google_search_retrieval(grounding)] if grounding else None
    for attempt in range(5):
        try:
            logging.debug(f"Invoking Gemini (Attempt {attempt + 1}/5)...")
            response = model.generate_content(prompt, tools=tools)
            if response.candidates[0].finish_reason.name != "STOP":
                logging.warning(f"Gemini call finished with non-stop reason: {response.candidates[0].finish_reason.name}")
                continue
            parsed_json = json.loads(response.text)
            jsonschema.validate(instance=parsed_json, schema=schema)
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

def _find_bausteine_recursive(group: Dict[str, Any], found_bausteine: List[Dict[str, Any]]):
    """ A. FIX: Truly recursive function to find all groups with class 'baustein'. """
    # Check the current group first
    if group.get("class") == "baustein":
        found_bausteine.append(group)
    
    # Then, recurse into any of its children
    for subgroup in group.get("groups", []):
        _find_bausteine_recursive(subgroup, found_bausteine)

def find_target_bausteine(catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    """ Finds all Baustein-groups under the specified main technical groups. """
    target_bausteine = []
    for main_group in catalog.get("catalog", {}).get("groups", []):
        if main_group.get("id") in TECHNICAL_MAIN_GROUPS:
            # A. FIX: Start the recursive search from the main group itself.
            _find_bausteine_recursive(main_group, target_bausteine)
    logging.info(f"Found {len(target_bausteine)} target Bausteine to process.")
    return target_bausteine

def get_prose_from_part(parts_list: List[Dict[str, Any]], part_name: str) -> Optional[str]:
    for part in parts_list:
        if part.get("name") == part_name:
            return part.get("prose")
    return None

def _collect_child_baustein_ids(group: Dict[str, Any], collected_ids: List[str]):
    """ C. FIX: Helper to recursively collect IDs of child Bausteine. """
    if group.get("class") == "baustein":
        collected_ids.append(group.get("id"))
    for subgroup in group.get("groups", []):
        _collect_child_baustein_ids(subgroup, collected_ids)

def expand_baustein_ids(catalog: Dict[str, Any], ids_to_expand: List[str]) -> List[str]:
    """ C. FIX: Fully implements the expansion of general Baustein IDs. """
    expanded_ids = []
    all_groups = catalog.get("catalog", {}).get("groups", [])
    for an_id in ids_to_expand:
        group = _find_group_by_id(all_groups, an_id)
        if not group:
            continue
        # If the group is a Baustein itself, add it.
        if group.get("class") == "baustein":
            expanded_ids.append(an_id)
        # If it has sub-groups, collect all Bausteine under it.
        if "groups" in group:
            _collect_child_baustein_ids(group, expanded_ids)
    
    unique_ids = sorted(list(set(expanded_ids)))
    logging.debug(f"Expanded {ids_to_expand} to {unique_ids}")
    return unique_ids

def get_controls_from_baustein_list(catalog: Dict[str, Any], baustein_ids: List[str]) -> List[Dict[str, Any]]:
    # ... (no changes needed here)
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
    # ... (no changes needed here)
    component = {"component-definition": {"uuid": str(uuid.uuid4()),"metadata": {"title": f"Component for Baustein {baustein_group.get('id')}: {baustein_group.get('title')}","last-modified": datetime.now(timezone.utc).isoformat(),"version": "1.0.0","oscal-version": "1.1.2","remarks": f"AI-enriched component for {baustein_group.get('id')}."}, "components": [{"uuid": str(uuid.uuid4()),"type": "service","title": baustein_group.get('title'),"description": f"Implementation of controls for Baustein {baustein_group.get('id')}.","control-implementations": []}]}}
    controls = baustein_group.get("controls", [])
    if controls:
        impl_reqs = [{"uuid": str(uuid.uuid4()), "control-id": c.get("id"), "description": f"Base implementation for control {c.get('id')}."} for c in controls]
        component["component-definition"]["components"][0]["control-implementations"].append({"uuid": str(uuid.uuid4()),"source": source_url,"description": f"Implementation for all controls in group {baustein_group.get('id')}: {baustein_group.get('title')}","implemented-requirements": impl_reqs})
    return component

def add_controls_to_component(component: Dict[str, Any], controls_with_reasons: List[Dict[str, Any]], group_title: str, source_url: str):
    """ B. FIX: Accepts controls with reasons and adds them to the component. """
    if not controls_with_reasons:
        return
    
    impl_reqs = []
    for item in controls_with_reasons:
        control, reason = item['control'], item['reason']
        impl_reqs.append({
            "uuid": str(uuid.uuid4()),
            "control-id": control.get("id"),
            "description": f"AI-Reason: {reason}"
        })
    
    component["component-definition"]["components"][0]["control-implementations"].append({
        "uuid": str(uuid.uuid4()),
        "source": source_url,
        "description": group_title,
        "implemented-requirements": impl_reqs
    })
    logging.info(f"Added new implementation group '{group_title}' with {len(controls_with_reasons)} controls.")


# --- Main Processing Logic ---
def process_single_baustein(baustein_group: Dict[str, Any], catalog: Dict[str, Any], prompts: Dict[str, str], schemas: Dict[str, Any], source_url: str) -> Optional[Dict[str, Any]]:
    # ... (This function has significant changes to handle the new data structures)
    baustein_id = baustein_group.get("id")
    logging.info(f"--- Starting processing for Baustein {baustein_id} ---")

    component = create_base_component(baustein_group, source_url)
    usage_prose = get_prose_from_part(baustein_group.get("parts", []), "usage")
    dependent_controls_with_reasons = []

    if not usage_prose:
        logging.warning(f"No 'usage' prose found for {baustein_id}. Skipping dependency extraction (C.2-C.5).")
    else:
        prompt = prompts["extract_dependencies"].format(schema=json.dumps(schemas["dependency"]), prose=usage_prose)
        dependency_result = invoke_gemini(prompt, schemas["dependency"])
        
        if dependency_result and dependency_result.get("dependencies"):
            # B. FIX: Extract IDs from the new object structure
            dependency_ids_raw = [item['id'] for item in dependency_result.get("dependencies", [])]
            dependency_ids = expand_baustein_ids(catalog, dependency_ids_raw) # C. FIX uses this now
            
            if dependency_ids:
                candidate_controls = get_controls_from_baustein_list(catalog, dependency_ids)
                if candidate_controls:
                    context_prose = {"introduction": get_prose_from_part(baustein_group.get("parts", []), "introduction"),"objective": get_prose_from_part(baustein_group.get("parts", []), "objective"), "usage": usage_prose}
                    candidate_json = json.dumps([{"id": c.get("id"), "title": c.get("title")} for c in candidate_controls])
                    prompt = prompts["filter_controls"].format(schema=json.dumps(schemas["control_filter"]), introduction_prose=context_prose["introduction"], objective_prose=context_prose["objective"], usage_prose=context_prose["usage"], candidate_controls_json=candidate_json)
                    filter_result = invoke_gemini(prompt, schemas["control_filter"])
                    
                    if filter_result and filter_result.get("approved_controls"):
                        approved_items = {item['id']: item['reason'] for item in filter_result.get("approved_controls")}
                        for c in candidate_controls:
                            if c.get("id") in approved_items:
                                dependent_controls_with_reasons.append({"control": c, "reason": approved_items[c.get("id")]})
    
    # C.5: Add dependency controls
    add_controls_to_component(component, dependent_controls_with_reasons, "Dependencies from related Bausteine", source_url)
    
    # C.6: Filter generic controls
    generic_candidate_controls = get_controls_from_baustein_list(catalog, GENERIC_CONTROLS_FOR_STEP_6)
    context_prose = {"introduction": get_prose_from_part(baustein_group.get("parts", []), "introduction"), "objective": get_prose_from_part(baustein_group.get("parts", []), "objective"), "usage": usage_prose or "N/A"}
    candidate_json = json.dumps([{"id": c.get("id"), "title": c.get("title")} for c in generic_candidate_controls])
    prompt = prompts["filter_controls"].format(schema=json.dumps(schemas["control_filter"]), introduction_prose=context_prose["introduction"], objective_prose=context_prose["objective"], usage_prose=context_prose["usage"], candidate_controls_json=candidate_json)
    generic_filter_result = invoke_gemini(prompt, schemas["control_filter"])
    
    generic_controls_with_reasons = []
    if generic_filter_result and generic_filter_result.get("approved_controls"):
        approved_items = {item['id']: item['reason'] for item in generic_filter_result.get("approved_controls")}
        for c in generic_candidate_controls:
            if c.get("id") in approved_items:
                generic_controls_with_reasons.append({"control": c, "reason": approved_items[c.get("id")]})

    # C.7: Add generic controls
    add_controls_to_component(component, generic_controls_with_reasons, "SYS.0 Generic Controls", source_url)

    logging.info(f"--- Finished processing for Baustein {baustein_id} ---")
    return component

def main():
    # ... (no changes needed in main)
    try:
        config = Config()
        setup_logging(config.is_test_mode)
    except ValueError as e:
        logging.critical(f"Configuration error: {e}")
        sys.exit(1)

    try:
        prompts = {"extract_dependencies": load_external_file("prompts/extract_dependencies_prompt.txt"), "filter_controls": load_external_file("prompts/filter_controls_prompt.txt")}
        schemas = {"dependency": json.loads(load_external_file("schemas/dependency_schema.json")), "control_filter": json.loads(load_external_file("schemas/control_filter_schema.json")), "oscal_component": json.loads(load_external_file("schemas/oscal_component_schema.json"))}
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