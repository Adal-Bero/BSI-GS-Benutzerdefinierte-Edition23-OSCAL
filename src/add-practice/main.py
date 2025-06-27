import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from jsonschema import validate, ValidationError

from config import (
    BUCKET_NAME,
    EXISTING_JSON_GCS_PATH,
    OUTPUT_PREFIX,
    TEST_MODE,
    setup_logging,
)
from gcs_utils import read_json_from_gcs, write_json_to_gcs
from gemini_utils import generate_practice_for_control, MAX_CONCURRENT_REQUESTS

# Initialize logging as the first step
setup_logging()
logger = logging.getLogger(__name__)


def load_json_schema(schema_path: str) -> dict:
    """Loads a JSON schema from a local file."""
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.critical(f"Schema file not found at: {schema_path}", exc_info=True)
        raise
    except json.JSONDecodeError:
        logger.critical(f"Invalid JSON in schema file: {schema_path}", exc_info=True)
        raise


def find_all_controls(catalog: dict) -> list[dict]:
    """Recursively finds all controls in the catalog data."""
    controls = []
    
    def recurse(obj):
        if isinstance(obj, dict):
            if "controls" in obj and isinstance(obj["controls"], list):
                controls.extend(obj["controls"])
            for key, value in obj.items():
                recurse(value)
        elif isinstance(obj, list):
            for item in obj:
                recurse(item)

    recurse(catalog)
    return controls


async def main():
    """Main function to orchestrate the data processing pipeline."""
    logger.info("Starting the practice generation process.")

    # Load the final result schema for final validation
    result_schema = load_json_schema("schemas/catalog.schema.json")

    # Load the catalog from GCS
    catalog_data = await read_json_from_gcs(BUCKET_NAME, EXISTING_JSON_GCS_PATH)

    if not catalog_data:
        logger.critical("Failed to load catalog data from GCS. Aborting process.")
        return

    # Extract all controls from the catalog using the structure from the user's sample
    all_controls = find_all_controls(catalog_data)

    logger.info(f"Found {len(all_controls)} total controls to process.")

    # Apply test mode limit if active
    if TEST_MODE:
        limit = 3
        all_controls = all_controls[:limit]
        logger.warning(f"TEST_MODE is active. Processing only the first {len(all_controls)} controls.")

    # Process controls in parallel using a semaphore to limit concurrency
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    tasks = []
    
    async def process_with_semaphore(control):
        async with semaphore:
            return await generate_practice_for_control(control)

    for control in all_controls:
        tasks.append(process_with_semaphore(control))
        
    results = await asyncio.gather(*tasks)

    # Update controls with generated practices
    updated_controls_count = 0
    for control, practice_part in zip(all_controls, results):
        if practice_part:
            # Ensure the 'parts' list exists
            if "parts" not in control:
                control["parts"] = []
            
            # Remove existing practice part to prevent duplicates on re-runs
            control["parts"] = [p for p in control["parts"] if p.get("name") != "practice"]
            
            # Add the new practice part
            control["parts"].append(practice_part)
            updated_controls_count += 1
            logger.debug(f"Updated control {control.get('id')} with new practice.")

    logger.info(f"Successfully generated and added practices for {updated_controls_count}/{len(all_controls)} controls.")

    # Update metadata
    catalog_data["catalog"]["metadata"]["last-modified"] = datetime.now(timezone.utc).isoformat()
    
    # Validate the final catalog against the result schema
    try:
        validate(instance=catalog_data, schema=result_schema)
        logger.info("Final catalog validation successful.")
    except ValidationError as e:
        logger.error(f"Final catalog validation failed: {e.message}", exc_info=True)
        # We will still save the file but log a clear error.
    
    # Save the updated catalog to GCS
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_filename = os.path.basename(EXISTING_JSON_GCS_PATH).replace('.json', '')
    output_filename = f"{base_filename}_with_practices_{timestamp}.json"
    output_path = os.path.join(OUTPUT_PREFIX, output_filename)

    await write_json_to_gcs(BUCKET_NAME, output_path, catalog_data)
    logger.info(f"Practice generation process finished. Updated catalog saved to: gs://{BUCKET_NAME}/{output_path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"An unhandled exception occurred in main: {e}", exc_info=True)