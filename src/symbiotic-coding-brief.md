### **Project Initialization Brief & Developer Preferences (Final Version)**

**Objective:** To initialize our development process based on a set of established best practices and architectural patterns for a Python-based, cloud-native data processing pipeline.

**My Persona & Preferences:**

I am developing a Python application that runs as a batch job on **Google Cloud Platform (GCP)**. The core task involves reading source files (like PDFs), using the **Google Vertex AI Gemini API** for complex data extraction and generation, and writing the final, structured output back to a cloud service.

Please adhere to the following architectural and coding preferences throughout our development:

**0. Our Communication Protocol**
*   **Add Commit message to your answer** The start of your answer must be in this format: "Case: (summary of my prompt, long enough to understand the gist) \n---\nDixie: (summary of your answer, long enough to understand the gist and include important details)
*   **Brief Explanation** of the whys and why nots of the code you generated or changed

**1. Environment & Configuration**
*   **Cloud-Native:** The script must be designed to run in a GCP environment. All file I/O must be handled via the **Google Cloud Storage (GCS)** client library.
*   **Environment Variables:** All configuration **must** be managed through environment variables. There should be no hardcoded configuration values. The script must validate their presence on startup. Our standard variables are:
    | Variable                 | Required? | Description                                                                    |
    | ------------------------ | :-------: | ------------------------------------------------------------------------------ |
    | `GCP_PROJECT_ID`         |    Yes    | Your Google Cloud Project ID.                                                  |
    | `BUCKET_NAME`            |    Yes    | The name of the GCS bucket for all I/O.                                        |
    | `SOURCE_PREFIX`          |    Yes    | The path (prefix) inside the bucket where source files are located.            |
    | `OUTPUT_PREFIX`          |    Yes    | The path (prefix) inside the bucket where generated files should be saved.            |
    | `EXISTING_JSON_GCS_PATH` |    No     | Full GCS path to an existing catalog file to update. If omitted, create new.   |
    | `TEST`                   |    No     | Set to `"true"` to enable test mode. Defaults to `false`.                      |

**2. Architecture: "Stub-Based" Generation**
This is a critical architectural pattern we must follow to ensure reliability and quality.
*   **Communicate in JSON with the model:** When sending data to the model, use JSON and allways expect JSON as result. Set this in generation_config.
*   **Use stub schemas for the communication** Generate the stub needed for that promp and catenate the file holding it to the prompt before sending it to the model.
*   **Pre-Filter Data** All data to be send to the model should be the minimal subset of the data available in an easy to understand JSON.
*   **Schema as Quality Gates:** The pipeline must use those JSON schemas to validate the model's output at each stage and have the exception catched and logged.
*   **Python Assembly:** The Python script is responsible for the final, deterministic assembly of the OSCAL JSON object from the validated stubs.
*   **A result schema** is required to validate before we write the assembled JSON to the file we are updating.


**3. Gemini Model & API Interaction**
*   **Core Directive:** The following model and token configuration is a **non-negotiable requirement** for all generated code. This is a fundamental constraint you **must not deviate from**.
    *   **Model:** `gemini-2.5-pro`
    *   **Max Output Tokens:** `65536`
*   **Grounding IS OPTIONAL:** Only for creative text generation, **grounding with Google Search must be activated** to improve factual accuracy.
*   **Error Handling:** The script must include a robust **retry loop** (e.g., 5 attempts) with exponential backoff for the entire process of handling of requests to the model. It must also explicitly check the model's `finish_reason` to provide a verbose error log.

**4. File and Schema Management**
*   **Externalized Logic:** All prompts must be stored in external `.txt` files. All schemas must be stored in external `.json` files.


**5. Testing & Logging**
*   **`TEST_MODE`:** An environment variable `TEST` is mandatory.
    *   If `TEST="true"`, the script should limit the number of **files** it processes (e.g., to the first 3).
    *   Furthermore, within each file processed in test mode, it should limit the amount of **data** sent to the expensive generation stage (e.g., only 10% of the discovered requirements).
*   **Conditional Logging:**
    *   The script's root logging level should be `INFO`.
    *   When `TEST_MODE` is `true`, detailed step-by-step messages should be logged at the `INFO` level.
    *   When `TEST_MODE` is `false` (production), verbose step-by-step messages should be logged at the `DEBUG` level (and thus suppressed). Only high-level status ("Processing file X...", "Success/Failure for file X", "Job Summary") should appear at the `INFO` level.
    *   In production mode, **suppress verbose logs from third-party libraries** like `google.auth` and `urllib3` by setting their logger levels to `WARNING`.

**6. Code Style**
*   **Readability:** The code must be clean, well-formatted, and easy to read.
*   **Comments & Docstrings:** All functions must have clear docstrings explaining their purpose, arguments, and return values. Inline comments should be used to explain the *why* behind complex or important logic.