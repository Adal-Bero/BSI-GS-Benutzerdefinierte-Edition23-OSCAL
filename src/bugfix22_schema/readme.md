fixin #22

---

# BSI Grundschutz OSCAL Converter

## 1. Goal of this Project

This script is a batch processing tool designed to convert legacy BSI Grundschutz security catalogs from a custom JSON format into a **valid, interoperable, and OSCAL-compliant format.**

The primary goal is to transform data that, while structured, does not conform to the official OSCAL standard. By converting it, we enable the use of standard OSCAL tools for automation, compliance tracking, and integration with other security platforms.

## 2. The Problem: The Legacy Schema vs. OSCAL

The original JSON format used a non-standard, nested structure to represent variations of a single security requirement. Specifically, different **Maturity Levels** for a BSI control were modeled as nested `controls` within a parent `bsiControl` object.

This approach has several critical flaws:
-   **It is not valid OSCAL.** Standard validation tools will reject it.
-   **It breaks tool compatibility.** Automated systems cannot parse or reference these requirements correctly.
-   **It is semantically incorrect.** A maturity level is a variation of a single requirement, not a distinct child requirement.

## 3. The Solution: Core Schema Conversions

This script performs a series of targeted transformations to map the legacy structure to a valid OSCAL model. The core principle is to represent each BSI requirement as a single, flat `control` and model its variations (Maturity Levels) as structured `parts` within that control.

Here are the key conversions the script performs:

#### A. Flattening Nested Controls
The primary transformation is to flatten the nested structure.
-   **Before:** A `bsiControl` object contains an array of nested `maturityControl` objects.
-   **After:** A single, top-level `control` object is created.

#### B. Modeling Variants as OSCAL `parts`
Each `maturityControl` from the old schema is converted into a single OSCAL `part` within the new `control`.
-   The `title` from the old object (e.g., `"Maturity Level 1: Partial"`) becomes the new `part.title`.
-   A `class` is derived from the maturity level property to allow for machine filtering (e.g., `class: "maturity-level-partial"`).
-   A static `name` (e.g., `"maturity-level-description"`) is added to the `part`, as the `name` field is **required by the OSCAL standard** to define the part's purpose.

#### C. Standardizing Sub-Part Names
The descriptive parts within each maturity level are renamed to align with standard OSCAL terminology.
-   `"name": "control"` becomes `"name": "statement"`.
-   `"name": "implementation_note"` becomes `"name": "guidance"`.
-   `"name": "audit_procedure"` becomes `"name": "assessment-method"`.

#### D. UUID Generation
To ensure every component is uniquely identifiable and linkable (a core feature of OSCAL), the script generates and injects a new `uuid` for every:
-   `group` (BSI Baustein)
-   `control` (BSI Requirement)
-   `part` (Maturity Level and its sub-parts)

#### E. Namespace Normalization
All custom BSI-specific properties (`level`, `phase`, etc.) are assigned a standard namespace (`ns`) to prevent conflicts with OSCAL-native properties.

### Example Transformation

This shows how the script converts the data for a single maturity level.

**BEFORE (Legacy Schema Snippet):**
```json
// This is one element in the "controls" array of a "bsiControl"
{
  "id": "isms.1.a1-m2",
  "title": "Maturity Level 2: Foundational",
  "props": [ { "name": "maturity-level", "value": "Foundational" } ],
  "parts": [
    { "name": "control", "prose": "The overall responsibility..." },
    { "name": "implementation_note", "prose": "The assignment of responsibility..." }
  ]
}
```

**AFTER (OSCAL-Compliant `part`):**
```json
// This is one element in the "parts" array of a single OSCAL "control"
{
  "uuid": "e8a9f2b1-3c1d-4e6f-8a9b-2c8d7e6f5c4d", // Newly generated
  "name": "maturity-level-description",              // Standardized name (required by OSCAL)
  "title": "Maturity Level 2: Foundational",        // Preserved from old object
  "class": "maturity-level-foundational",           // Derived from props
  "parts": [
    {
      "uuid": "f1d2c3b4-a5e6-4d7c-8b9a-1e0f9d8c7b6a",
      "name": "statement",                           // Renamed from "control"
      "prose": "The overall responsibility..."
    },
    {
      "uuid": "a9b8c7d6-e5f4-4c3b-8a9e-1f0e9d8c7b6a",
      "name": "guidance",                            // Renamed from "implementation_note"
      "prose": "The assignment of responsibility..."
    }
  ]
}
```

## 4. Script Operation (Workflow)

The script (`main.py`) operates as a batch job:
1.  **Lists Files:** It lists all objects in the GCS directory specified by `GCS_INPUT_DIRECTORY`.
2.  **Filters:** It skips any non-`.json` files and intelligently ignores its own output directory (`converted/`).
3.  **Loops & Processes:** For each valid JSON file, it performs the full set of conversions described above.
4.  **Handles Errors:** If a file is malformed or causes a transformation error, the script logs the failure and continues to the next file, ensuring the batch job completes.
5.  **Writes Output:** The transformed, OSCAL-compliant file is written to the `converted/` directory in the same GCS bucket, preserving the original filename.

## 5. Configuration

The script is configured entirely through environment variables.

| Variable              | Required? | Description                                                                                                                              |
| --------------------- | :-------: | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `GCP_PROJECT_ID`      |    Yes    | Your Google Cloud Project ID.                                                                                                            |
| `BUCKET_NAME`         |    Yes    | The name of the GCS bucket containing the source files.                                                                                  |
| `GCS_INPUT_DIRECTORY` |    Yes    | The path (prefix) inside the bucket where the source `.json` files are located. A trailing slash is recommended (e.g., `results/source/`). |
| `TEST`                |    No     | Set to `"true"` (case-insensitive) to enable test mode, which processes only ~5% of the data. Defaults to `false`.                      |

## 6. Setup and Execution

### Prerequisites
-   Python 3.8+
-   [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install) authenticated.

### Installation
```bash
pip install -r requirements.txt
```

### Running the Script
```bash
# Set the required environment variables
export GCP_PROJECT_ID="your-gcp-project-id"
export BUCKET_NAME="your-company-bucket"
export GCS_INPUT_DIRECTORY="bsi/catalogs/raw/"
export TEST="false"

# Execute the script
python main.py
```