#!/bin/bash

# This script sets environment variables for main.py

# Replace with your actual values
export GCP_PROJECT_ID="ai-ensemble"
export BUCKET_NAME="us_rag_storage_1"
export EXISTING_JSON_GCS_PATH="results/BSI_GS_OSCAL_current_2023_benutzerdefinierte.json"
export OUTPUT_PREFIX="components/"

export TEST=true
echo "Environment variables set for main.py. You can now run the script."

