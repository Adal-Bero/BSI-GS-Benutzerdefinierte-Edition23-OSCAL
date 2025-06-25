import os
import json
import logging
import uuid
import sys
import re
from datetime import datetime, timezone

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

def parse_gcs_path(gcs_path: str) -> tuple[str, str]:
    """
    Parses a GCS path into bucket name and blob path.

    Args:
        gcs_path: The full GCS path (e.g., "gs://bucket-name/path/to/file.json").

    Returns:
        A tuple containing the bucket name and the blob path.
    
    Raises:
        ValueError: If the GCS path format is invalid.
    """
    match = re.match(r"gs://([^/]+)/(.+)", gcs_path)
    if not match:
        raise ValueError(f"Invalid GCS path format: '{gcs_path}'. Must be in the format 'gs://bucket-name/blob-path'.")
    bucket_name = match.group(1)
    blob_path = match.group(2)
    return bucket_name, blob_path


def download_json_from_gcs(client: storage.Client, bucket_name: str, blob_path: str) -> dict:
    """Downloads and parses a JSON file from a GCS bucket."""
    try:
        logging.debug(f"Attempting to download JSON from gs://{bucket_name}/{blob_path}")
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        json_data = json.loads(blob.download_as_string())
        logging.info(f"Successfully downloaded JSON from gs://{bucket_name}/{blob_path}")
        return json_data
    except exceptions.NotFound:
        logging.error(f"GCS Error: File not found at gs://{bucket_name}/{blob_path}")
        raise
    except json.JSONDecodeError:
        logging.error(f"Error: Failed to decode JSON from gs://{bucket_name}/{blob_path}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred during GCS download: {e}")
        raise

def upload_json_to_gcs(client: storage.Client, bucket_name: str, blob_path: str, data: dict):
    """Uploads a Python dictionary as a JSON file to a GCS bucket."""
    try:
        logging.debug(f"Attempting to upload JSON to gs://{bucket_name}/{blob_path}")
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(data, indent=2),
            content_type="application/json"
        )
        logging.info(f"Successfully uploaded JSON to gs://{bucket_name}/{blob_path}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during GCS upload: {e}")
        raise

def create_process_component(catalog: dict, profile_source: str) -> dict:
    """
    Creates an OSCAL component definition from specified groups in a source catalog.

    Args:
        catalog: The source OSCAL catalog as a Python dictionary.
        profile_source: The source URL or identifier of the profile being implemented.

    Returns:
        A dictionary representing the new OSCAL component definition.
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
                "remarks": "Component automatically generated from Prozess-Baustein groups."
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

    # This is the list where we will aggregate all implemented controls.
    control_implementations = component_definition["component-definition"]["components"][0]["control-implementations"]

    if 'groups' not in catalog.get('catalog', {}):
        logging.warning("Source catalog does not contain 'groups'. Cannot create component.")
        return component_definition
    
    # Iterate through all groups in the source catalog
    for group in catalog["catalog"]["groups"]:
        group_id = group.get("id")
        if group_id in PROCESS_GROUP_IDS:
            logging.debug(f"Processing group: {group_id} - {group.get('title')}")
            
            if "controls" not in group:
                logging.debug(f"Group {group_id} has no controls to implement. Skipping.")
                continue

            # For each control in the selected group, create an implementation entry
            for control in group["controls"]:
                control_id = control.get("id")
                if not control_id:
                    continue

                impl_req = {
                    "uuid": str(uuid.uuid4()),
                    "control-id": control_id,
                    "description": f"Implementation for control {control_id} as defined in the source catalog."
                }

                control_implementations.append({
                    "uuid": str(uuid.uuid4()),
                    "source": profile_source, # Link back to the catalog this comes from
                    "description": f"Implementation for control {control_id} from group {group_id}.",
                    "implemented-requirements": [impl_req]
                })

    logging.info(f"Component definition created with {len(control_implementations)} control implementations.")
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
        storage_client = storage.Client(project=config.gcp_project_id)

        # For this script, the source GCS path is mandatory.
        if not config.existing_json_gcs_path:
            raise ValueError("Configuration error: The EXISTING_JSON_GCS_PATH environment variable must be set.")
        
        # Parse the GCS path and validate the bucket against our configuration.
        source_bucket, source_blob_path = parse_gcs_path(config.existing_json_gcs_path)
        if source_bucket != config.bucket_name:
            raise ValueError(
                f"Bucket name mismatch: The bucket in EXISTING_JSON_GCS_PATH ('{source_bucket}') "
                f"does not match the configured BUCKET_NAME ('{config.bucket_name}')."
            )

        # 1. Download the source catalog
        source_catalog = download_json_from_gcs(
            storage_client,
            config.bucket_name,
            source_blob_path
        )
        catalog_source_url = source_catalog.get("catalog", {}).get("metadata", {}).get("source", config.existing_json_gcs_path)

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