import os
import sys
import json
import logging
import uuid
import asyncio
import random
from datetime import datetime, timezone

import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason, GenerationResponse
from google.cloud import storage
from google.api_core.exceptions import ResourceExhausted, InternalServerError, ServiceUnavailable, NotFound
from jsonschema import validate, ValidationError

# --- Standard Google Cloud Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
try:
    GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
    BUCKET_NAME = os.environ["BUCKET_NAME"]
    SOURCE_PREFIX = os.environ.get("SOURCE_PREFIX")
    EXISTING_JSON_GCS_PATH = os.environ.get("EXISTING_JSON_GCS_PATH")

except KeyError as e:
    logging.critical(f"FATAL: A required environment variable is missing: {e}")
    sys.exit(1)

FINAL_RESULT_PREFIX = "results/"


CONCURRENT_REQUEST_LIMIT = 5
TEST_MODE = os.environ.get("TEST", "false").lower() == 'true'
PROMPT_FILE = os.environ.get("PROMPT_FILE", "prompt.txt")
# --- MODIFIED: Use the new schema file for PARTS stubs ---
SCHEMA_FILE = os.environ.get("SCHEMA_FILE", "bsi_parts_stub_schema.json")
MAX_RETRIES = 5
INITIAL_BACKOFF_BASE_SECONDS = 5
JITTER_FACTOR = 0.5

generation_config = {
      "response_mime_type": "application/json",
      "max_output_tokens": 65536
}

if TEST_MODE:
    logging.warning("--- testcases ---")
    SOURCE_PREFIX = "testcases/"


# --- Load Prompt and Stub Schema ---
def get_prompt_and_schema(prompt_path, schema_path):
    """Reads the prompt and the JSON stub schema from specified files."""
    try:
        logging.info(f"Loading prompt from '{prompt_path}' and stub schema from '{schema_path}'...")
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_text = f.read()
        with open(schema_path, 'r', encoding='utf-8') as f:
            stub_schema = json.load(f)
        logging.info("Successfully loaded prompt and stub schema files.")
        return prompt_text, stub_schema
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Required file not found: {e}.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON schema from '{schema_path}': {e}")

# --- Initialize Google Cloud Clients ---
try:
    stub_prompt_text, loaded_stub_schema = get_prompt_and_schema(PROMPT_FILE, SCHEMA_FILE)
    vertexai.init(project=GCP_PROJECT_ID, location="us-central1")
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    gemini_model = GenerativeModel("gemini-2.5-pro")

except Exception as e:
    logging.critical(f"FATAL: Failed to initialize or load essential files: {e}")
    sys.exit(1)


def load_existing_catalog(bucket, gcs_path):
    """Loads an existing JSON catalog from GCS. Exits on failure."""
    if not gcs_path:
        logging.critical("FATAL: No existing JSON path (EXISTING_JSON_GCS_PATH) provided.")
        sys.exit(1)

    logging.info(f"Attempting to load base catalog from gs://{bucket.name}/{gcs_path}...")
    blob = bucket.blob(gcs_path)
    try:
        existing_json_string = blob.download_as_string()
        existing_catalog = json.loads(existing_json_string)
        if "catalog" in existing_catalog and "groups" in existing_catalog["catalog"]:
             logging.info("Successfully loaded and parsed base catalog.")
             return existing_catalog
        else:
            raise ValueError("Base JSON is missing required structure ('catalog' or 'catalog.groups').")

    except NotFound:
        logging.critical(f"FATAL: The base catalog was not found at gs://{bucket.name}/{gcs_path}.")
        sys.exit(1)
    except (json.JSONDecodeError, ValueError) as e:
        logging.critical(f"FATAL: Failed to parse the base JSON file at {gcs_path}: {e}.")
        sys.exit(1)


async def process_single_blob_for_stub(blob, semaphore, prompt, schema_for_validation):
    """Asynchronously processes a single PDF to generate a small, validated JSON stub."""
    async with semaphore:
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                logging.info(f"Processing {blob.name} for stub (Attempt {attempt + 1}/{MAX_RETRIES})...")
                gcs_uri = f"gs://{BUCKET_NAME}/{blob.name}"
                file_part = Part.from_uri(gcs_uri, mime_type="application/pdf")
                contents = [file_part, prompt]

                response = await gemini_model.generate_content_async(
                    contents,
                    generation_config=generation_config,
                )

                if response.candidates and response.candidates[0].finish_reason != FinishReason.STOP:
                    raise ValueError(f"Model finish reason was not STOP: {response.candidates[0].finish_reason.name}")

                if not response.text:
                    raise ValueError("Model returned empty response text.")

                parsed_stub = json.loads(response.text)
                validate(instance=parsed_stub, schema=schema_for_validation)

                logging.info(f"Successfully generated and validated stub for Baustein: {parsed_stub.get('id')}")
                return parsed_stub

            except (ResourceExhausted, InternalServerError, ServiceUnavailable, ValueError, json.JSONDecodeError, ValidationError) as e:
                logging.warning(f"Attempt {attempt + 1} for {blob.name} failed: {type(e).__name__}: {e}")
                if attempt + 1 == MAX_RETRIES:
                    logging.error(f"All {MAX_RETRIES} attempts failed for {blob.name}. Skipping file.")
                    return None
                base_delay = INITIAL_BACKOFF_BASE_SECONDS * (2 ** attempt)
                backoff_time = base_delay + random.uniform(0, base_delay * JITTER_FACTOR)
                await asyncio.sleep(backoff_time)
            except Exception as e:
                logging.error(f"Unexpected critical error processing {blob.name}: {e}")
                return None


def merge_stubs_into_catalog(stubs, base_catalog):
    """
    Merges a list of JSON stubs (containing 'parts') into the base catalog.
    It finds the matching Baustein by ID and replaces its 'parts' array.
    """
    logging.info(f"Starting merge of {len(stubs)} stubs into base catalog...")
    final_catalog = base_catalog

    baustein_map = {}
    for main_group in final_catalog.get("catalog", {}).get("groups", []):
        for baustein_group in main_group.get("groups", []):
            if baustein_group.get("id"):
                baustein_map[baustein_group["id"]] = baustein_group

    stubs_merged_count = 0
    for stub in stubs:
        if stub is None:
            continue

        baustein_id = stub.get("id")
        if not baustein_id:
            logging.warning("Skipping a stub because it is missing an 'id'.")
            continue

        if baustein_id in baustein_map:
            target_baustein = baustein_map[baustein_id]
            # --- MODIFIED: Assign to the 'parts' key instead of 'props' ---
            target_baustein["parts"] = stub["parts"]
            logging.info(f"Successfully merged PARTS for Baustein '{baustein_id}'.")
            stubs_merged_count += 1
        else:
            logging.warning(f"Found stub for Baustein ID '{baustein_id}' but this ID does not exist in the base catalog. Stub will be ignored.")

    logging.info(f"Merge complete. Merged {stubs_merged_count} stubs into the catalog.")
    final_catalog["catalog"]["metadata"]["last-modified"] = datetime.now(timezone.utc).isoformat()
    return final_catalog


async def main():
    """Main asynchronous function to orchestrate the entire job."""
    base_catalog = load_existing_catalog(bucket, EXISTING_JSON_GCS_PATH)

    all_blobs = list(storage_client.list_blobs(BUCKET_NAME, prefix=SOURCE_PREFIX))
    files_to_process = [blob for blob in all_blobs if blob.name.endswith('.pdf')]

    if not files_to_process:
        logging.warning("No PDF files found in source directory to process. Exiting.")
        return

    logging.info(f"Found {len(files_to_process)} PDF files to process.")

    if TEST_MODE:
        logging.warning("--- TEST MODE ENABLED: Limiting processing to the first 3 files. ---")
        files_to_process = files_to_process[:3]

    semaphore = asyncio.Semaphore(CONCURRENT_REQUEST_LIMIT)

    tasks = [process_single_blob_for_stub(blob, semaphore, stub_prompt_text, loaded_stub_schema) for blob in files_to_process]

    logging.info(f"Dispatching tasks to generate PARTS stubs with a concurrency of {CONCURRENT_REQUEST_LIMIT}...")
    all_stubs = await asyncio.gather(*tasks)
    logging.info("All stub generation tasks have completed.")

    final_catalog = merge_stubs_into_catalog(all_stubs, base_catalog)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_filename = f"{FINAL_RESULT_PREFIX}MERGED_BSI_Catalog_with_Parts_{timestamp}.json"
    output_blob = bucket.blob(output_filename)
    output_blob.upload_from_string(
        data=json.dumps(final_catalog, indent=2, ensure_ascii=False),
        content_type="application/json"
    )
    logging.info(f"Successfully uploaded final merged catalog to gs://{BUCKET_NAME}/{output_filename}")


if __name__ == "__main__":
    asyncio.run(main())