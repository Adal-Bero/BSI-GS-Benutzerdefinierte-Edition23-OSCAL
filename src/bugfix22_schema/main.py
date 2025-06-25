import json
import uuid
import sys
import os
import logging
from typing import Dict, Any
from datetime import datetime, timezone

# --- Standard Logging & Environment Variable Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from google.cloud import storage
except ImportError:
    logging.critical("The 'google-cloud-storage' library is not installed. Please install it using: pip install google-cloud-storage")
    sys.exit(1)

try:
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    BUCKET_NAME = os.getenv("BUCKET_NAME")
    GCS_INPUT_DIRECTORY = os.getenv("GCS_INPUT_DIRECTORY")
    IS_TEST_MODE = os.getenv("TEST", "false").lower() == 'true'

    required_vars = ["GCP_PROJECT_ID", "BUCKET_NAME", "GCS_INPUT_DIRECTORY"]
    missing_vars = [var for var in required_vars if not globals()[var]]
    if missing_vars: raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

except ValueError as e:
    logging.critical(e); sys.exit(1)

# --- Static Configuration ---
BSI_PROPERTY_NAMESPACE = "https://www.bsi.bund.de/ns/grundschutz"
MATURITY_PART_NAME_MAP = {"control": "statement", "implementation_note": "guidance", "audit_procedure": "assessment-method"}
OUTPUT_FOLDER = "converted"

# --- GCS Helper Functions (Unchanged) ---
def download_blob_as_json(client, bucket_name, source_path) -> Dict[str, Any]:
    try:
        bucket = client.bucket(bucket_name); blob = bucket.blob(source_path)
        logging.info(f"Downloading gs://{bucket_name}/{source_path}...")
        return json.loads(blob.download_as_string())
    except Exception as e:
        logging.error(f"Failed to download or parse blob from gs://{bucket_name}/{source_path}.", exc_info=True); raise

def upload_json_as_blob(client, bucket_name, data, destination_path):
    try:
        bucket = client.bucket(bucket_name); blob = bucket.blob(destination_path)
        logging.info(f"Uploading converted file to gs://{bucket_name}/{destination_path}...")
        json_string = json.dumps(data, indent=2, ensure_ascii=False)
        blob.upload_from_string(json_string, content_type="application/json")
    except Exception as e:
        logging.error(f"Failed to upload blob to gs://{bucket_name}/{destination_path}.", exc_info=True); raise

# --- Transformation Logic (CORRECTED) ---

def harden_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    if 'oscal-version' not in metadata: metadata['oscal-version'] = "1.1.2"
    if 'last-modified' not in metadata: metadata['last-modified'] = datetime.now(timezone.utc).isoformat()
    if 'version' not in metadata: metadata['version'] = "1.0.0"
    if 'title' not in metadata: metadata['title'] = "Untitled BSI Grundschutz Catalog"
    return metadata

def transform_maturity_part(old_part: Dict[str, Any]) -> Dict[str, Any]:
    old_name = old_part.get("name"); new_name = MATURITY_PART_NAME_MAP.get(old_name, "unknown-part-type")
    return {"name": new_name, "prose": old_part.get("prose", "")}

def transform_maturity_control_to_part(old_mc: Dict[str, Any]) -> Dict[str, Any]:
    level_value = "unknown"
    for prop in old_mc.get("props", []):
        if prop.get("name") == "maturity-level": level_value = prop.get("value", "unknown").lower().replace(" ", "-"); break
    
    # Corrected: Parts do not have UUIDs. They can have an optional 'id'.
    # We will map the old ID to the new one.
    part_data = {
        "id": old_mc.get("id"),
        "name": "maturity-level-description",
        "title": old_mc.get("title"),
        "class": f"maturity-level-{level_value}",
        "parts": [transform_maturity_part(p) for p in old_mc.get("parts", [])]
    }
    return part_data

def transform_bsi_control_to_oscal_control(old_ctrl: Dict[str, Any]) -> Dict[str, Any]:
    # Corrected: This function no longer generates a UUID.
    props = old_ctrl.get("props", []); [p.update({'ns': BSI_PROPERTY_NAMESPACE}) for p in props]
    return {
        "id": old_ctrl.get("id"),
        "title": old_ctrl.get("title"),
        "class": "technical",
        "props": props,
        "parts": [transform_maturity_control_to_part(mc) for mc in old_ctrl.get("controls", [])]
    }

def transform_group(old_group: Dict[str, Any], is_nested: bool = False) -> Dict[str, Any]:
    """
    Transforms a group. The 'is_nested' flag determines if it's a Baustein.
    Corrected: This function no longer generates a UUID.
    """
    new_group = {"id": old_group.get("id"), "title": old_group.get("title")}
    
    if is_nested:
        new_group["class"] = "baustein"
    else:
        original_class = old_group.get("class")
        if original_class:
            new_group["class"] = original_class

    if "groups" in old_group and old_group["groups"]:
        new_group["groups"] = [transform_group(g, is_nested=True) for g in old_group.get("groups", [])]
        
    if "controls" in old_group and old_group["controls"]:
        new_controls = []
        for ctrl in old_group.get("controls", []):
            try:
                if "props" in ctrl and "controls" in ctrl: new_controls.append(transform_bsi_control_to_oscal_control(ctrl))
                else: new_controls.append(ctrl)
            except Exception: logging.error(f"Skipping control '{ctrl.get('id', 'N/A')}' due to a transformation error.", exc_info=True)
        new_group["controls"] = new_controls
    return new_group

# --- Main Execution ---
def main():
    logging.info("Batch conversion job starting...")
    client = storage.Client(project=GCP_PROJECT_ID)
    
    blobs = list(client.list_blobs(BUCKET_NAME, prefix=GCS_INPUT_DIRECTORY))
    if not blobs: logging.warning(f"No files found in gs://{BUCKET_NAME}/{GCS_INPUT_DIRECTORY}. Exiting."); return

    processed_count, failed_count = 0, 0
    for blob in blobs:
        source_path = blob.name
        if not source_path.lower().endswith('.json') or f"/{OUTPUT_FOLDER}/" in f"/{source_path}": continue

        logging.info(f"--- Processing file: {source_path} ---")
        try:
            old_data = download_blob_as_json(client, BUCKET_NAME, source_path)
            old_catalog = old_data.get("catalog", {})
            metadata = harden_metadata(old_catalog.get("metadata", {}))

            groups_to_process = old_catalog.get("groups", [])
            if IS_TEST_MODE and groups_to_process:
                slice_index = max(1, int(len(groups_to_process) * 0.05))
                groups_to_process = groups_to_process[:slice_index]
                logging.warning(f"TEST MODE ACTIVE: Processing a subset of groups for {source_path}.")

            new_catalog = {
                "catalog": {
                    "uuid": old_catalog.get("uuid", str(uuid.uuid4())), # Top-level catalog still needs a UUID
                    "metadata": metadata,
                    "groups": [transform_group(g) for g in groups_to_process]
                }
            }

            output_gcs_path = f"{OUTPUT_FOLDER}/{os.path.basename(source_path)}"
            upload_json_as_blob(client, BUCKET_NAME, new_catalog, output_gcs_path)
            processed_count += 1
        except Exception as e:
            logging.error(f"FATAL: Failed to process file {source_path}. Error: {e}", exc_info=True)
            failed_count += 1
            continue

    logging.info("--- Batch Job Summary ---")
    logging.info(f"Successfully processed: {processed_count} file(s).")
    logging.info(f"Failed to process: {failed_count} file(s).")
    logging.info("Batch conversion job finished.")

if __name__ == "__main__":
    main()