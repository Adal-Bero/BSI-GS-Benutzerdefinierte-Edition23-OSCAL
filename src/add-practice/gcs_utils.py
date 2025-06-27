import json
import logging

from google.cloud import storage
from google.api_core.exceptions import GoogleAPICallError

from config import GCP_PROJECT_ID

logger = logging.getLogger(__name__)


def get_gcs_client():
    """Initializes and returns a GCS client."""
    try:
        return storage.Client(project=GCP_PROJECT_ID)
    except Exception as e:
        logger.error(f"Failed to initialize GCS client: {e}")
        raise


async def read_json_from_gcs(bucket_name: str, blob_name: str) -> dict | None:
    """Reads and parses a JSON file from GCS.

    Args:
        bucket_name: The name of the GCS bucket.
        blob_name: The full path to the blob within the bucket.

    Returns:
        A dictionary parsed from the JSON file, or None on error.
    """
    logger.info(f"Reading JSON from gs://{bucket_name}/{blob_name}")
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        if not blob.exists():
            logger.error(f"File not found in GCS: gs://{bucket_name}/{blob_name}")
            return None

        json_data = blob.download_as_string()
        return json.loads(json_data)
    except GoogleAPICallError as e:
        logger.error(f"GCS API error while reading gs://{bucket_name}/{blob_name}: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from gs://{bucket_name}/{blob_name}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while reading from GCS: {e}")
    return None


async def write_json_to_gcs(bucket_name: str, blob_name: str, data: dict):
    """Writes a dictionary to a JSON file in GCS.

    Args:
        bucket_name: The name of the GCS bucket.
        blob_name: The full path for the new blob.
        data: The dictionary to write as JSON.
    """
    logger.info(f"Writing JSON to gs://{bucket_name}/{blob_name}")
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        blob.upload_from_string(json_data, content_type="application/json")
        logger.info(f"Successfully wrote to gs://{bucket_name}/{blob_name}")
    except GoogleAPICallError as e:
        logger.error(f"GCS API error while writing to gs://{bucket_name}/{blob_name}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while writing to GCS: {e}")