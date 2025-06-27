import json
import logging

from google.cloud import storage
from google.api_core.exceptions import NotFound

from config import BUCKET_NAME

logger = logging.getLogger(__name__)
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

def list_blobs(prefix):
    """Lists all blobs in the bucket with the given prefix."""
    logger.info(f"Listing files in gs://{BUCKET_NAME}/{prefix}")
    return list(bucket.list_blobs(prefix=prefix))

def read_json_from_gcs(gcs_path):
    """Reads and parses a JSON file from GCS, returning None if not found."""
    blob = bucket.blob(gcs_path)
    try:
        logging.info(f"Reading JSON from gs://{BUCKET_NAME}/{gcs_path}...")
        return json.loads(blob.download_as_string())
    except NotFound:
        logger.warning(f"File not found at gs://{BUCKET_NAME}/{gcs_path}. Will start fresh.")
        return None
    except Exception as e:
        logger.error(f"Failed to read or parse JSON from gs://{BUCKET_NAME}/{gcs_path}: {e}")
        raise # Re-raise other errors to be handled by the caller

def write_json_to_gcs(gcs_path, data):
    """Writes a dictionary to a JSON file in GCS."""
    logger.info(f"Writing JSON to gs://{BUCKET_NAME}/{gcs_path}")
    blob = bucket.blob(gcs_path)
    try:
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        blob.upload_from_string(json_data, content_type="application/json")
        logger.info(f"Successfully wrote to gs://{BUCKET_NAME}/{gcs_path}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while writing to gs://{BUCKET_NAME}/{gcs_path}: {e}")
        raise