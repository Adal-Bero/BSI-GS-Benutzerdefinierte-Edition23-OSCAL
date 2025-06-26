import os
import json
import logging
import uuid
import sys
from datetime import datetime, timezone
from typing import Dict, Any

from google.cloud import storage
from google.api_core import exceptions
import jsonschema

# Define the specific Baustein Group IDs to be included in the process component.
PROCESS_GROUP_IDS = [
    "ISMS",  # ISMS: Sicherheitsmanagement
    "ORP",   # ORP: Organisation und Personal
    "CON",   # CON: Konzeption und Vorgehensweise
    "OPS",   # OPS: Betrieb
    "DER",   # DER: Detektion und Reaktion
]

class Config:
    """
    Manages and validates all environment-based configuration for the application.
    """
    def __init__(self):
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID")
        self.bucket_name = os.getenv("BUCKET_NAME")
        self.output_prefix = os.getenv("OUTPUT_PREFIX", "components")
        self.existing_json_gcs_path = os.getenv("EXISTING_JSON_GCS_PATH")
        self.is_test_mode = os.getenv("TEST", "false").lower() == "true"

        self.validate()

    def validate(self):
        """Raises ValueError if required configuration is missing."""
        required_vars = {
            "GCP_PROJECT_ID": self.gcp_project_id,
            "BUCKET_NAME": self.bucket_name,
        }
        missing_vars = [k for k, v in required_vars.items() if not v]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

def setup_logging(is_test_mode: bool):
    """Configures logging based on the execution mode."""
    log_level = logging.DEBUG if is_test_mode else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )

    if not is_test_mode:
        # Suppress verbose logs from third-party libraries in production
        logging.getLogger("google.auth").setLevel(logging.WARNING)
        logging.getLogger("google.api_core").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    
    logging.info(f"Logging initialized. Test mode: {is_test_mode}")


def download_json_from_gcs(client: storage.Client, bucket_name: str, blob_path: str) -> dict:
    """Downloads and parses a JSON file from a GCS bucket."""
    full_gcs_path = f"gs://{bucket_name}/{blob_path}"
    try:
        logging.debug(f"Attempting to download JSON from {full_gcs_path}")
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        json_data = json.loads(blob.download_as_string())
        logging.info(f"Successfully downloaded JSON from {full_gcs_path}")
        return json_data
    except exceptions.NotFound:
        logging.error(f"GCS Error: File not found at {full_gcs_path}")
        raise
    except json.JSONDecodeError:
        logging.error(f"Error: Failed to decode JSON from {full_gcs_path}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred during GCS download from {full_gcs_path}: {e}")
        raise

def upload_json_to_gcs(client: storage.Client, bucket_name: str, blob_path: str, data: dict):
    """Uploads a Python dictionary as a JSON file to a GCS bucket."""
    full_gcs_path = f"gs://{bucket_name}/{blob_path}"
    try:
        logging.debug(f"Attempting to upload JSON to {full_gcs_path}")
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(data, indent=2),
            content_type="application/json"
        )
        logging.info(f"Successfully uploaded JSON to {full_gcs_path}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during GCS upload to {full_gcs_path}: {e}")
        raise

def create_process_component(catalog: dict, profile_source: str) -> dict:
    """
    Creates an OSCAL component definition by grouping controls by their parent "Baustein".
    
    This method creates one `control-implementation` per Baustein-group.
    """
    logging.info("Starting creation of process component definition.")
    component_uuid = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc).isoformat()

    component_definition = {
        "component-definition": {
            "uuid": component_uuid,
            "metadata": {
                "title": "Prozess-Bausteine Component Definition",
                "last-modified": now_utc,
                "version": "1.0.0",
                "oscal-version": "1.1.2",
                "remarks": "Component automatically generated from Prozess-Baustein groups, with controls grouped by Baustein."
            },
            "components": [{
                "uuid": str(uuid.uuid4()),
                "type": "service",
                "title": "Prozess-Komponente",
                "description": "This component represents the implementation of all controls from the IT-Grundschutz Prozess-Bausteine.",
                "control-implementations": []
            }]
        }
    }

    # This is the list where we will aggregate the control-implementation objects.
    control_implementations = component_definition["component-definition"]["components"][0]["control-implementations"]
    
    catalog_groups = catalog.get("catalog", {}).get("groups", [])
    if not catalog_groups:
        logging.warning("Source catalog does not contain 'groups'. Cannot create component.")
        return component_definition
    
    total_controls_implemented = 0
    # Iterate through the top-level groups of the catalog (e.g., "ISMS", "ORP")
    for main_group in catalog_groups:
        if main_group.get("id") not in PROCESS_GROUP_IDS:
            continue

        logging.info(f"Processing main group: {main_group.get('id')}")

        # Iterate through the nested "Baustein" groups within the main group
        for baustein_group in main_group.get("groups", []):
            group_id = baustein_group.get("id")
            group_title = baustein_group.get("title")
            logging.debug(f"Found Baustein-group: {group_id} - {group_title}")
            
            implemented_reqs_for_this_group = []
            if "controls" in baustein_group:
                for control in baustein_group["controls"]:
                    control_id = control.get("id")
                    if not control_id:
                        continue
                    
                    # Create the implementation for a single control
                    implemented_reqs_for_this_group.append({
                        "uuid": str(uuid.uuid4()),
                        "control-id": control_id,
                        "description": f"Implementation for control {control_id} as defined in the source catalog."
                    })
            
            # If we found any controls in this Baustein, create a parent control-implementation for them.
            if implemented_reqs_for_this_group:
                logging.debug(f"Creating control-implementation for group '{group_id}' with {len(implemented_reqs_for_this_group)} controls.")
                control_implementations.append({
                    "uuid": str(uuid.uuid4()),
                    "source": profile_source,
                    "description": f"Implementation for all controls in group {group_id}: {group_title}",
                    "implemented-requirements": implemented_reqs_for_this_group
                })
                total_controls_implemented += len(implemented_reqs_for_this_group)

    logging.info(f"Component definition created with {len(control_implementations)} control-implementation groups, "
                 f"totaling {total_controls_implemented} implemented controls.")
    return component_definition


def main():
    """Main execution function."""
    try:
        config = Config()
        setup_logging(config.is_test_mode)
    except ValueError as e:
        logging.critical(f"Configuration error: {e}")
        sys.exit(1)

    try:
        if not config.existing_json_gcs_path:
            raise ValueError("Configuration error: The EXISTING_JSON_GCS_PATH environment variable must be set.")
        
        source_blob_path = config.existing_json_gcs_path
        storage_client = storage.Client(project=config.gcp_project_id)

        # 1. Download the source catalog
        source_catalog = download_json_from_gcs(
            storage_client,
            config.bucket_name,
            source_blob_path
        )
        
        full_gcs_source_path = f"gs://{config.bucket_name}/{source_blob_path}"
        catalog_source_url = source_catalog.get("catalog", {}).get("metadata", {}).get("source", full_gcs_source_path)

        # 2. Create the component definition
        component_data = create_process_component(source_catalog, catalog_source_url)
        
        # 3. Validate the generated component against our schema
        logging.info("Validating generated component against schema...")
        schema_path = os.path.join(os.path.dirname(__file__), 'schemas', 'oscal_component_schema.json')
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        jsonschema.validate(instance=component_data, schema=schema)
        logging.info("Schema validation successful.")

        # 4. Upload the final component file
        output_blob_path = os.path.join(config.output_prefix, "process_component.json")
        upload_json_to_gcs(
            storage_client,
            config.bucket_name,
            output_blob_path,
            component_data
        )

        logging.info("Job completed successfully.")

    except Exception as e:
        logging.critical(f"A critical error occurred: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()