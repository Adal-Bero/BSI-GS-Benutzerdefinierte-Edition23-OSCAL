# BSI Grundschutz to Enriched OSCAL: The Automated Conversion Pipeline

This project provides a powerful, automated pipeline for converting BSI Grundschutz "Baustein" PDF documents into a rich, structured, and OSCAL-compliant JSON format. It leverages the advanced capabilities of Google's `gemini-2.5-pro` model to not only extract the content but to deeply enrich it with a multi-level maturity model, practice classifications, and other critical metadata, making the final catalog immediately useful for analysis and compliance management.

The system is designed to run as a serverless **Google Cloud Run Job** and operates **incrementally**. It intelligently reads an existing master OSCAL catalog, processes new or updated PDFs, and seamlessly merges the results by adding new "Bausteine" or overwriting existing ones.

### Key Features

*   **Fully Automated Conversion:** Transforms raw PDF content into structured OSCAL JSON with zero manual intervention.
*   **Incremental Updates:** Intelligently adds new Bausteine or overwrites existing ones in a master catalog file, making the process repeatable and efficient.
*   **Deep Enrichment:** The pipeline doesn't just extract text; it enriches every control with:
    *   **A 5-Level Maturity Model:** Generates five distinct maturity levels for every single requirement.
    *   **Practice Classification:** Assigns each control to a functional security practice (e.g., GOV, RISK, ARCH).
    *   **Control Class:** Classifies each control as `Technical`, `Operational`, or `Management`.
    *   **CIA Tenant Analysis:** Determines if a control impacts Confidentiality, Integrity, or Availability.
*   **Contextual Information:** Extracts introductory chapters (Einleitung, Zielsetzung) and the complete threat landscape (Gefährdungslage) into structured `parts`, providing vital context directly within the catalog.
*   **Robust & Modular:** The code is logically separated into modules for configuration, GCS interaction, and AI processing, following modern best practices.

---

## The Multi-Stage AI Architecture

To maximize reliability and quality, this pipeline avoids a single, monolithic AI request. Instead, it uses a sophisticated multi-stage architecture that delegates tasks based on their complexity.

```
+------------------+     +------------------------+
| Baustein PDF     | --> |   STAGE 1: DISCOVERY   |
| (in GCS)         |     | (Reliable Extraction)  |
+------------------+     +-----------+------------+
                                     |
                                     v
                  +------------------------------------+
                  |  Validated Requirements Stub JSON  |
                  +------------------+-----------------+
                                     |
           +-------------------------+-------------------------+
           |                                                   |
           v                                                   v
+------------------------+                        +-------------------------+
| STAGE 2: GENERATION    |                        | STAGE 3: ENRICHMENT     |
| (Creative Prose)       |                        | (Analytical AI)         |
+------------------------+                        +-------------------------+
           |                                                   |
           v                                                   v
  +------------------+                                +-------------------+
  | Validated Prose  |                                | Validated Class & |
  |      JSON        |                                |   Practice JSON   |
  +------------------+                                +-------------------+
           |                                                   |
           +---------------------+-----------------------------+
                                 |
                                 v
                 +-------------------------------+
                 |    PYTHON FINAL ASSEMBLY      |
                 |  (Deterministic Structuring)  |
                 +---------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   |  Final Validated OSCAL JSON |
                   +-----------------------------+

```

### Stage 1: Discovery (Low Complexity, High Reliability)
The process begins by sending the raw PDF to the AI with a focused prompt (`prompt_discovery.txt`). The AI's only job is to perform a simple, reliable extraction of the high-level structure: the Baustein ID, titles, contextual parts, and a simple list of all requirements with their original text. This output is immediately validated against `discovery_stub_schema.json`.

### Stage 2 & 3: Parallel AI Processing (High Quality, High Efficiency)
Once the list of requirements is successfully discovered, the script launches two AI tasks *in parallel* to maximize efficiency:
1.  **Generation Task:** Uses `prompt_generation.txt` to perform the complex, creative work of writing the detailed prose for all 5 maturity levels for the entire batch of requirements. The result is validated against `generation_stub_schema.json`.
2.  **Enrichment Task:** Uses `prompt_enrichment.txt` to perform the analytical work of classifying each requirement's `practice`, `class`, and CIA impact. The result is validated against `enrichment_stub_schema.json`.

### Final Assembly (Deterministic)
The Python script (`main.py`) acts as the final, deterministic assembler. It gathers the validated data from all three stages and builds the final, complete OSCAL `control` objects. These are merged into the main catalog, which is then validated one last time against the master `bsi_gk_2023_oscal_schema.json` before being saved.

This architecture is superior because it delegates tasks appropriately:
-   **AI:** Handles creative text generation and complex classification.
-   **Python:** Handles strict data structuring, validation, and final assembly.

---

## File Descriptions

### Core Logic
*   **`main.py`:** The main orchestrator. It reads configuration, finds files, manages the `asyncio` event loop for parallel processing, calls the utility modules, and assembles the final OSCAL catalog.
*   **`config.py`:** A centralized hub for all configuration. It loads environment variables, defines static file paths and retry settings, and sets up the logger.
*   **`gcs_utils.py`:** A dedicated module for all interactions with Google Cloud Storage (listing, reading, writing files).
*   **`gemini_utils.py`:** The "AI brain" of the project. It handles initializing the Gemini model and contains the core logic for the multi-stage AI processing pipeline.

### Prompts
*   **`prompt_discovery.txt`:** Instructs the AI on how to perform the initial, reliable extraction of structure and text from a PDF.
*   **`prompt_generation.txt`:** A detailed, expert-level prompt that guides the AI in the creative task of writing the 5-level maturity prose.
*   **`prompt_enrichment.txt`:** A precise, analytical prompt that instructs the AI to classify each control's practice, class, and CIA impact.

### Schemas (Quality Gates)
*   **`bsi_gk_2023_oscal_schema.json`:** The final, strict JSON Schema that defines a valid BSI Grundschutz OSCAL catalog. It is used to validate the final output before saving.
*   **`discovery_stub_schema.json`:** Validates the output of the Discovery stage.
*   **`generation_stub_schema.json`:** Validates the output of the Generation stage.
*   **`enrichment_stub_schema.json`:** Validates the output of the Enrichment stage.

### Other Files
*   **`requirements.txt`:** Lists all necessary Python libraries.
*   **`Dockerfile`:** Defines the container image for deployment on Google Cloud Run.

---
## Enriched Data Models

### 1. The 5-Level Maturity Model
Every requirement extracted from the BSI Grundschutz is mapped to a 5-level maturity model, enabling a granular evaluation of implementation quality.
*   **Stufe 1: Partial (Teilweise umgesetzt)**
*   **Stufe 2: Foundational (Grundlegend umgesetzt)**
*   **Stufe 3: Defined (Definiert umgesetzt)** - **Baseline**
*   **Stufe 4: Enhanced (Erweitert umgesetzt)**
*   **Stufe 5: Comprehensive (Umfassend umgesetzt)**

### 2. Practice Classification
Each control is assigned to a functional practice domain, such as `GOV` (Governance), `RISK` (Risk Management), or `SYS` (System Protection). This allows for a role-based or function-based view of the security controls.

### 3. Control Class & CIA Tenants
*   **Class:** Every control is classified as `Technical`, `Operational`, or `Management` based on the NIST standard, clarifying how the control is implemented.
*   **CIA:** Each control is tagged with booleans (`effective_on_c`, `effective_on_i`, `effective_on_a`) to show its primary impact on Confidentiality, Integrity, and Availability.

---

## Configuration & Local Execution

The script is configured entirely through environment variables.

| Variable                 | Required? | Description                                                                                                                              |
| ------------------------ | :-------: | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `GCP_PROJECT_ID`         |    Yes    | Your Google Cloud Project ID.                                                                                                            |
| `BUCKET_NAME`            |    Yes    | The name of the GCS bucket containing the source files and where results will be written.                                                  |
| `SOURCE_PREFIX`          |    Yes    | The path (prefix) inside the bucket where the source `.pdf` files are located. A trailing slash is recommended (e.g., `source_pdfs/`).     |
| `EXISTING_JSON_GCS_PATH` |    No     | The full GCS path to an existing merged catalog file to update. If not provided, a new catalog is created from scratch.                   |
| `TEST`                   |    No     | Set to `"true"` (case-insensitive) to enable test mode. This processes only the first 3 PDFs and only 10% of the requirements within each. |


### Running Locally
1.  **Authenticate with Google Cloud:**
    ```bash
    gcloud auth application-default login
    ```
2.  **Set Environment Variables (example):**
    ```bash
    export GCP_PROJECT_ID="your-gcp-project-id"
    export BUCKET_NAME="your-company-bucket"
    export SOURCE_PREFIX="bsi/source_pdfs/"
    export EXISTING_JSON_GCS_PATH="results/MERGED_BSI_Catalog_latest.json"
    export TEST="false"
    ```
3.  **Install Dependencies and Run:**
    ```bash
    pip install -r requirements.txt
    python main.py
    ```

---

## Deployment on Google Cloud Run Jobs

This application is designed to run as a serverless batch job.

### Step 1: Build the Container Image
Use Google Cloud Build to create a container image from the `Dockerfile` and push it to the Artifact Registry.

```bash
gcloud builds submit --tag gcr.io/[YOUR_PROJECT_ID]/g2oscal-pipeline .
```

### Step 2: Create the Cloud Run Job
Create a job that uses the container image and passes the necessary environment variables.

```bash
gcloud run jobs create g2oscal-job \
  --image gcr.io/[YOUR_PROJECT_ID]/g2oscal-pipeline \
  --region [YOUR_GCP_REGION] \
  --task-timeout=3600 \
  --set-env-vars="GCP_PROJECT_ID=[YOUR_PROJECT_ID]" \
  --set-env-vars="BUCKET_NAME=[YOUR_BUCKET_NAME]" \
  --set-env-vars="SOURCE_PREFIX=bsi/source_pdfs/" \
  --set-env-vars="EXISTING_JSON_GCS_PATH=results/MERGED_BSI_Catalog_latest.json" \
  --set-env-vars="TEST=false"
```
> **Note:** Ensure the service account used by the job has "Vertex AI User" and "Storage Object Admin" roles.

### Step 3: Execute the Job
You can run the job manually from the console or trigger it via the command line.

```bash
gcloud run jobs execute g2oscal-job --region [YOUR_GCP_REGION]
```
The job will run, process all new PDFs, merge them into the catalog, and save the new version to Google Cloud Storage.
