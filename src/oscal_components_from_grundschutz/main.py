import os
import json
import logging
import uuid
import sys
import time
import random
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
# FIX: Import libraries for concurrency
import concurrent.futures
import threading

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
EXCLUDED_DEPENDENCY_IDS = ["ISMS.1", "APP.6"]
# FIX: Define the concurrency limit as a constant
MAX_CONCURRENT_JOBS = 10


# --- Configuration & Setup (No Changes) ---
# ... (All functions from Config to get_direct_controls_from_baustein are unchanged) ...
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
def render_prompt(template: str, context: Dict[str, Any]) -> str:
    try:
        return template.format(**context)
    except KeyError as e:
        logging.error(f"Failed to render prompt. Missing key: {e}. Context keys provided: {list(context.keys())}")
        raise
def invoke_gemini(prompt: str, schema: Dict[str, Any], grounding: bool = False) -> Optional[Dict[str, Any]]:
    sanitized_schema = {k: v for k, v in schema.items() if k not in UNSUPPORTED_SCHEMA_KEYS}
    model = GenerativeModel("gemini-2.5-pro", generation_config=GenerationConfig(response_mime_type="application/json", response_schema=sanitized_schema))
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
        except exceptions.ResourceExhausted as e:
            logging.warning(f"API rate limit hit (ResourceExhausted). Attempt {attempt + 1}/5. Error: {e}")
            if attempt < 4:
                sleep_time = (2 ** (attempt + 1)) + random.uniform(0, 1)
                logging.info(f"Retrying after a longer backoff: {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            else: logging.error("API rate limit still exhausted after maximum retries.")
        except Exception as e:
            logging.error(f"An unexpected error occurred during Gemini invocation (Attempt {attempt + 1}): {e}", exc_info=True)
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
def load_external_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f: return f.read()
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
    if group.get("class") == "baustein": found_bausteine.append(group)
    for subgroup in group.get("groups", []): _find_bausteine_recursive(subgroup, found_bausteine)
def find_target_bausteine(catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    target_bausteine = []
    for main_group in catalog.get("catalog", {}).get("groups", []):
        if main_group.get("id") in TECHNICAL_MAIN_GROUPS:
            _find_bausteine_recursive(main_group, target_bausteine)
    logging.info(f"Found {len(target_bausteine)} target Bausteine to process.")
    return target_bausteine
def find_prose_by_part_name_recursive(parts_list: List[Dict[str, Any]], part_name: str) -> Optional[str]:
    for part in parts_list:
        if part.get("name") == part_name:
            return part.get("prose")
        if "parts" in part and part.get("parts"):
            found_prose = find_prose_by_part_name_recursive(part["parts"], part_name)
            if found_prose:
                return found_prose
    return None
def get_control_statement_prose(control: Dict[str, Any]) -> Optional[str]:
    for part in control.get("parts", []):
        if part.get("class") == "maturity-level-defined":
            return find_prose_by_part_name_recursive(part.get("parts", []), "statement")
    return None
def _collect_child_baustein_ids(group: Dict[str, Any], collected_ids: List[str]):
    if group.get("class") == "baustein": collected_ids.append(group.get("id"))
    for subgroup in group.get("groups", []): _collect_child_baustein_ids(subgroup, collected_ids)
def expand_baustein_ids(catalog: Dict[str, Any], ids_to_expand: List[str]) -> List[str]:
    expanded_ids = []
    all_groups = catalog.get("catalog", {}).get("groups", [])
    for an_id in ids_to_expand:
        group = _find_group_by_id(all_groups, an_id)
        if not group: continue
        if group.get("class") == "baustein": expanded_ids.append(an_id)
        if "groups" in group: _collect_child_baustein_ids(group, expanded_ids)
    unique_ids = sorted(list(set(expanded_ids)))
    logging.debug(f"Expanded {ids_to_expand} to {unique_ids}")
    return unique_ids
def _get_all_controls_from_group_recursive(group: Dict[str, Any], controls_list: List[Dict[str, Any]]):
    controls_list.extend(group.get("controls", []))
    for subgroup in group.get("groups", []):
        _get_all_controls_from_group_recursive(subgroup, controls_list)
def get_controls_from_baustein_list(catalog: Dict[str, Any], baustein_ids: List[str]) -> List[Dict[str, Any]]:
    all_controls = []
    all_groups = catalog.get("catalog", {}).get("groups", [])
    for b_id in baustein_ids:
        group = _find_group_by_id(all_groups, b_id)
        if group:
            _get_all_controls_from_group_recursive(group, all_controls)
    logging.debug(f"Fetched {len(all_controls)} controls from {len(baustein_ids)} Bausteine.")
    return all_controls
def _get_controls_by_id_recursive(group: Dict[str, Any], control_ids_to_find: set, found_controls: List[Dict[str, Any]]):
    for control in group.get("controls", []):
        if control.get("id") in control_ids_to_find:
            found_controls.append(control)
    for subgroup in group.get("groups", []):
        _get_controls_by_id_recursive(subgroup, control_ids_to_find, found_controls)
def get_controls_by_id(catalog: Dict[str, Any], control_ids: List[str]) -> List[Dict[str, Any]]:
    found_controls = []
    control_ids_to_find = set(control_ids)
    for group in catalog.get("catalog", {}).get("groups", []):
        _get_controls_by_id_recursive(group, control_ids_to_find, found_controls)
    logging.debug(f"Searched for {len(control_ids)} control IDs, found {len(found_controls)} matching controls.")
    return found_controls
def get_direct_controls_from_baustein(catalog: Dict[str, Any], baustein_id: str) -> List[Dict[str, Any]]:
    all_groups = catalog.get("catalog", {}).get("groups", [])
    group = _find_group_by_id(all_groups, baustein_id)
    if group: return group.get("controls", [])
    return []

# --- Component Manipulation Functions (No Changes) ---
def create_base_component(baustein_group: Dict[str, Any], source_url: str) -> Dict[str, Any]:
    component = {"component-definition": {"uuid": str(uuid.uuid4()),"metadata": {"title": f"Component for Baustein {baustein_group.get('id')}: {baustein_group.get('title')}","last-modified": datetime.now(timezone.utc).isoformat(),"version": "1.0.0","oscal-version": "1.1.2","remarks": f"AI-enriched component for {baustein_group.get('id')}."}, "components": [{"uuid": str(uuid.uuid4()),"type": "service","title": baustein_group.get('title'),"description": f"Implementation of controls for Baustein {baustein_group.get('id')}.","control-implementations": []}]}}
    all_base_controls = []
    _get_all_controls_from_group_recursive(baustein_group, all_base_controls)
    if all_base_controls:
        impl_reqs = [{"uuid": str(uuid.uuid4()), "control-id": c.get("id"), "description": f"Base implementation for control {c.get('id')}."} for c in all_base_controls]
        component["component-definition"]["components"][0]["control-implementations"].append({"uuid": str(uuid.uuid4()),"source": source_url,"description": f"Implementation for all controls in group {baustein_group.get('id')}: {baustein_group.get('title')}","implemented-requirements": impl_reqs})
    return component
def add_controls_to_component(component: Dict[str, Any], controls_with_reasons: List[Dict[str, Any]], group_title: str, source_url: str):
    if not controls_with_reasons: return
    impl_reqs = []
    for item in controls_with_reasons:
        control, reason = item['control'], item['reason']
        impl_reqs.append({"uuid": str(uuid.uuid4()),"control-id": control.get("id"),"description": f"AI-Begründung: {reason}"})
    component["component-definition"]["components"][0]["control-implementations"].append({"uuid": str(uuid.uuid4()),"source": source_url,"description": group_title,"implemented-requirements": impl_reqs})
    logging.info(f"Added new implementation group '{group_title}' with {len(controls_with_reasons)} controls.")


# --- Main Processing Logic ---
def process_single_baustein(baustein_group: Dict[str, Any], catalog: Dict[str, Any], prompts: Dict[str, str], schemas: Dict[str, Any], source_url: str) -> Optional[Dict[str, Any]]:
    # This function is now the core logic for a single thread/job
    # ... (No changes to the internal logic of this function) ...
    baustein_id = baustein_group.get("id")
    logging.info(f"--- Starting processing for Baustein {baustein_id} ---")
    component = create_base_component(baustein_group, source_url)
    is_app_baustein = baustein_id.startswith("APP.")
    dependent_controls, generic_controls = [], []
    parts_list = baustein_group.get("parts", [])
    if is_app_baustein:
        logging.info(f"{baustein_id} is an APP Baustein. Deterministically adding APP.6 and skipping AI dependency analysis.")
        app6_controls = get_direct_controls_from_baustein(catalog, "APP.6")
        app6_with_reasons = [{"control": c, "reason": "Obligatorische Basisanforderung für alle APP-Bausteine."} for c in app6_controls]
        add_controls_to_component(component, app6_with_reasons, "Basiskomponente APP.6 Allgemeine Software", source_url)
        logging.info("Skipping generic controls for APP Baustein.")
    else:
        usage_prose = find_prose_by_part_name_recursive(parts_list, "usage")
        if usage_prose:
            dep_context = {"schema": json.dumps(schemas["dependency"]), "prose": usage_prose}
            dep_prompt = render_prompt(prompts["extract_dependencies"], dep_context)
            logging.debug(f"Full prompt for Gemini dependency extraction:\n---\n{dep_prompt}\n---")
            dependency_result = invoke_gemini(dep_prompt, schemas["dependency"])
            if dependency_result and dependency_result.get("dependencies"):
                dependency_items = dependency_result.get("dependencies", [])
                validated_items = [item for item in dependency_items if item['id'] in usage_prose]
                discarded_ids = [item['id'] for item in dependency_items if item['id'] not in usage_prose]
                if discarded_ids: logging.debug(f"Discarding hallucinated dependencies: {discarded_ids}")
                filtered_items = [item for item in validated_items if item['id'] not in EXCLUDED_DEPENDENCY_IDS]
                dependency_ids_raw = [item['id'] for item in filtered_items]
                dependency_ids = expand_baustein_ids(catalog, dependency_ids_raw)
                all_dependency_controls = get_controls_from_baustein_list(catalog, dependency_ids)
                dependent_controls = [c for c in all_dependency_controls if not c.get("id").startswith(baustein_id)]
        generic_controls = get_controls_by_id(catalog, GENERIC_CONTROLS_FOR_STEP_6)
    combined_list = dependent_controls + generic_controls
    if not combined_list:
        logging.info("No candidate controls to process. Finalizing component.")
        return component
    seen_ids = set()
    all_candidate_controls = [control for control in combined_list if not (control_id := control.get("id")) in seen_ids and not seen_ids.add(control_id)]
    logging.info(f"Preparing {len(all_candidate_controls)} unique candidate controls for AI filtering.")
    candidate_payload = [{"id": c.get("id"), "title": c.get("title"), "statement": get_control_statement_prose(c) or "Keine Angabe."} for c in all_candidate_controls]
    filter_context = {"schema": json.dumps(schemas["control_filter"]),"introduction_prose": find_prose_by_part_name_recursive(parts_list, "introduction") or "N/A","objective_prose": find_prose_by_part_name_recursive(parts_list, "objective") or "N/A","usage_prose": find_prose_by_part_name_recursive(parts_list, "usage") or "N/A","candidate_controls_json": json.dumps(candidate_payload, indent=2, ensure_ascii=False)}
    filter_prompt = render_prompt(prompts["filter_controls"], filter_context)
    logging.debug(f"Full prompt for Gemini control filtering:\n---\n{filter_prompt}\n---")
    filter_result = invoke_gemini(filter_prompt, schemas["control_filter"])
    if filter_result and filter_result.get("approved_controls"):
        approved_map = {item['id']: item['reason'] for item in filter_result.get("approved_controls")}
        approved_deps_with_reasons, approved_generics_with_reasons = [], []
        generic_control_ids = {c.get("id") for c in generic_controls}
        all_candidate_controls_map = {c.get("id"): c for c in all_candidate_controls}
        for control_id, reason in approved_map.items():
            control_obj = all_candidate_controls_map.get(control_id)
            if not control_obj: continue
            if control_id in generic_control_ids:
                approved_generics_with_reasons.append({"control": control_obj, "reason": reason})
            else:
                approved_deps_with_reasons.append({"control": control_obj, "reason": reason})
        add_controls_to_component(component, approved_deps_with_reasons, "Abhängigkeiten von verwandten Bausteinen", source_url)
        add_controls_to_component(component, approved_generics_with_reasons, "SYS.0 Allgemeine Kontrollen", source_url)
    logging.info(f"--- Finished processing for Baustein {baustein_id} ---")
    return component

def process_baustein_concurrently(semaphore: threading.Semaphore, baustein_group: Dict, **kwargs):
    """ FIX: New wrapper function to manage concurrency with a semaphore. """
    baustein_id = baustein_group.get("id", "Unknown")
    try:
        # Acquire a slot. This will block if all 10 slots are taken.
        with semaphore:
            final_component = process_single_baustein(baustein_group=baustein_group, **kwargs)
            
            if final_component:
                # Unpack kwargs needed for upload
                config = kwargs['config']
                storage_client = kwargs['storage_client']
                schemas = kwargs['schemas']
                
                # Final validation and upload is now done within the worker thread
                jsonschema.validate(instance=final_component, schema=schemas["oscal_component"])
                output_path = os.path.join(config.output_prefix, f"{baustein_id}.component.json")
                upload_json_to_gcs(storage_client, config.bucket_name, output_path, final_component)
    except Exception as e:
        logging.error(f"FATAL ERROR in worker while processing Baustein {baustein_id}. Skipping. Error: {e}", exc_info=True)


def main():
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
            if len(target_bausteine) > 3:
                logging.warning(f"TEST MODE: Processing a random sample of 3 out of {len(target_bausteine)} Bausteine.")
                target_bausteine = random.sample(target_bausteine, 3)
            else:
                logging.warning(f"TEST MODE: Processing all {len(target_bausteine)} available Bausteine (less than 3 found).")

        # FIX: Implement concurrent execution with ThreadPoolExecutor and Semaphore
        semaphore = threading.Semaphore(MAX_CONCURRENT_JOBS)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS) as executor:
            # Prepare arguments dictionary to pass to each worker
            worker_args = {
                "catalog": catalog,
                "prompts": prompts,
                "schemas": schemas,
                "source_url": source_url,
                "config": config,
                "storage_client": storage_client
            }
            
            # Submit all jobs to the executor
            futures = [executor.submit(process_baustein_concurrently, semaphore, baustein, **worker_args) for baustein in target_bausteine]
            
            # Wait for all futures to complete
            logging.info(f"Submitted {len(futures)} jobs to the thread pool. Waiting for completion...")
            for future in concurrent.futures.as_completed(futures):
                # This loop effectively waits. We can check for exceptions here if needed.
                try:
                    future.result()  # result() is None, but will re-raise exceptions from the worker
                except Exception as exc:
                    logging.error(f"A worker thread raised an unhandled exception: {exc}", exc_info=True)

        logging.info("Job completed.")
    except Exception as e:
        logging.critical(f"A critical, unrecoverable error occurred in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()