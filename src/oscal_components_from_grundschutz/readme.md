# AI-Driven OSCAL Component Generator

## Overview

This project contains a sophisticated Python script (`main.py`) designed to automatically generate enriched OSCAL component definitions from a BSI IT-Grundschutz catalog. The script identifies individual "Bausteine" (building blocks) from the source catalog, creates a base component definition for each, and then uses the Google Vertex AI Gemini Pro model to intelligently discover and add relevant controls from other Bausteine. To generate the rather static component for the "Process Modules" / "Prozessbausteine" a smaller script exists as well: `create_prozessbausteine_component.py`. This is run once.

The final output is a set of OSCAL-compliant JSON files, one for each technical Baustein, saved to a Google Cloud Storage (GCS) bucket.

## Core Operation

The script operates as a batch job with the following high-level workflow:

1.  **Initialization**: Loads configuration from environment variables and sets up logging.
2.  **Load Catalog**: Downloads the master IT-Grundschutz catalog from a specified GCS path.
3.  **Identify Targets**: Traverses the catalog to find all "Baustein" objects within the specified main technical groups (`APP`, `SYS`, `IND`, `NET`, `INF`).
4.  **Process Each Baustein**: For each target Baustein found, it executes the AI Enrichment Pipeline.
5.  **Save Output**: The resulting OSCAL component JSON is validated against a schema and uploaded to the specified output directory in GCS, named `<baustein-id>.component.json`.

## Configuration

All configuration is managed through environment variables. A `.env` file can be used for local development.

| Variable | Required? | Description |
| :--- | :---: | :--- |
| `GCP_PROJECT_ID` | Yes | Your Google Cloud Project ID. |
| `BUCKET_NAME` | Yes | The name of the GCS bucket for all I/O. |
| `EXISTING_JSON_GCS_PATH`| Yes | Path to the source catalog file, relative to the `BUCKET_NAME`. |
| `OUTPUT_PREFIX` | Yes | The path (prefix) inside the bucket where generated component files should be saved. |
| `TEST` | No | Set to `"true"` to enable test mode (processes first 3 Bausteine) and verbose `DEBUG` logging. Defaults to `false`. |

---

## The AI Enrichment Pipeline

The core logic of the script is a multi-step process that differs based on the type of Baustein being processed.

### Logic Path for **Non-APP** Bausteine (e.g., SYS, NET)

1.  **Base Component Creation**: A foundational OSCAL component is created containing only the controls directly defined within the current Baustein.

2.  **AI Dependency Extraction**:
    *   The `usage` prose of the Baustein is sent to the Gemini model.
    *   The model is prompted to identify and extract IDs of other Bausteine that are mentioned as direct dependencies.

3.  **Dependency Expansion**: 
    *   The script programmatically parses the source catalog to locate the specific text prose of the `part` with `name: "usage"` (**Chapter 1.3** of the BSI documentation) within the current Baustein.
    *   This text is sent to the Gemini model, which is prompted to identify and extract IDs of other Bausteine mentioned as direct dependencies.
    *   To prevent AI "hallucinations," a programmatic quality gate verifies that each dependency ID suggested by the AI is actually present as a substring in the original `usage` text before it is used.

4.  **Combined Control Filtering**:
    *   A master list of "candidate controls" is created by combining:
        *   All controls from the expanded dependency list (from Step 3).
        *   A static list of generic, high-value security controls (e.g., for logging, identity management).
    *   This combined list, along with the primary Baustein's context (introduction, objective, usage) and each candidate control's specific `statement` prose, is sent to the Gemini model in a **single API call**.
    *   The model is prompted to act as a quality gate, approving only those controls that are relevant, applicable, and add security value. It must provide a reason for each approval.

5.  **Final Assembly**: The controls approved by the AI are sorted into "Dependency" and "Generic" groups and added to the component file, each with its AI-generated reason.

### Logic Path for **APP** Bausteine

The process is simplified for application Bausteine to enforce specific business rules:

1.  **Base Component Creation**: Same as above.

2.  **Deterministic Dependency Addition**:
    *   The AI dependency extraction (Step 2 above) is **skipped**.
    *   The script deterministically adds all *direct* controls from **`APP.6 Allgemeine Software`** to the component with a standard, hardcoded reason.

3.  **Generic Control Filtering**:
    *   The script proceeds directly to filtering the static list of generic, high-value security controls against the APP Baustein's context, using the same AI quality gate process as in Step 4 for non-APP Bausteine.

4.  **Final Assembly**: The AI-approved generic controls are added to the component file.

---

## Business Rules & Special Logic

The script enforces several key business rules:

*   **APP Baustein Rule**: All Bausteine starting with `APP.` automatically get `APP.6` as a dependency and do not undergo AI dependency analysis.
*   **Dependency Exclusion**: `ISMS.1` and `APP.6` are always excluded from the list of potential AI-discovered dependencies to prevent circular or redundant additions.
*   **Self-Dependency Prevention**: A Baustein cannot be listed as a dependency of itself. The script filters out any controls that belong to the Baustein currently being processed.
*   **Schema as Quality Gate**: All communication with the AI model is governed by strict JSON schemas. The AI's output is validated against these schemas before being used, and the final OSCAL component is validated before being saved.

## Setup and Execution

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Authentication**: Ensure your environment is authenticated with Google Cloud. For local development, you can use:
    ```bash
    gcloud auth application-default login
    ```

3.  **Configuration**: Create a `.env` file in the project root and populate it with your configuration values (see table above).

4.  **Run the Script**:
    ```bash
    python main.py
    ```