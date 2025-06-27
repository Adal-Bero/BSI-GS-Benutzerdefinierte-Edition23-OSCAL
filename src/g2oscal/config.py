import os
import sys
import logging

# --- Environment Variable Loading ---
TEST_MODE = os.environ.get("TEST", "false").lower() == 'true'
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
SOURCE_PREFIX = os.environ.get("SOURCE_PREFIX")
EXISTING_JSON_GCS_PATH = os.environ.get("EXISTING_JSON_GCS_PATH")

# --- Static Configuration ---
FINAL_RESULT_PREFIX = "results/"
DISCOVERY_PROMPT_FILE = "prompt_discovery.txt"
GENERATION_PROMPT_FILE = "prompt_generation.txt"
ENRICHMENT_PROMPT_FILE = "prompt_enrichment.txt"
OSCAL_SCHEMA_FILE = "bsi_gk_2023_oscal_schema.json"
DISCOVERY_STUB_SCHEMA_FILE = "discovery_stub_schema.json"
GENERATION_STUB_SCHEMA_FILE = "generation_stub_schema.json"
ENRICHMENT_STUB_SCHEMA_FILE = "enrichment_stub_schema.json"

# --- Concurrency & Retry Config ---
CONCURRENT_REQUEST_LIMIT = 5
MAX_RETRIES = 5

def validate_env_vars():
    """Validates that all required environment variables are set."""
    required_vars = {
        "GCP_PROJECT_ID": GCP_PROJECT_ID,
        "BUCKET_NAME": BUCKET_NAME,
        "SOURCE_PREFIX": SOURCE_PREFIX,
    }
    missing_vars = [key for key, value in required_vars.items() if not value]
    if missing_vars:
        logging.basicConfig(level=logging.ERROR)
        error_message = f"FATAL: Missing required environment variables: {', '.join(missing_vars)}."
        logging.error(error_message)
        sys.exit(error_message)

def setup_logging():
    """Configures the root logger based on the TEST_MODE setting."""
    log_level = logging.DEBUG if TEST_MODE else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Suppress verbose logs from underlying libraries
    if not TEST_MODE:
        noisy_loggers = ["google.auth", "google.api_core", "urllib3"]
        for logger_name in noisy_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    logging.info(f"Logging initialized. TEST_MODE={TEST_MODE}")

# Validate required environment variables on import
validate_env_vars()