# BSI Grundschutz to OSCAL: The Automated Conversion Pipeline

This project provides a powerful, automated pipeline for converting BSI Grundschutz "Baustein" PDF documents into a rich, structured, and OSCAL-compliant JSON format. It leverages the advanced capabilities of Google's `gemini-2.5-pro` model to not only translate the content but to enrich it with a multi-level maturity model and contextual information, making the final catalog immediately useful for analysis and compliance management.

The system is designed to run as a serverless **Google Cloud Run Job** and operates **incrementally**. It intelligently reads an existing master OSCAL catalog, processes new or updated PDFs, and seamlessly merges the results by adding new "Bausteine" or overwriting existing ones.

### Key Features

*   **Fully Automated Conversion:** Transforms raw PDF content into structured OSCAL JSON with zero manual intervention.
*   **Incremental Updates:** Intelligently adds new Bausteine or overwrites existing ones in a master catalog file, making the process repeatable and efficient.
*   **Contextual Enrichment:** Extracts introductory chapters (Einleitung, Zielsetzung, Modellierung) and the complete threat landscape (Gefährdungslage) into structured `parts`, providing vital context directly within the catalog.
*   **5-Level Maturity Model:** Generates five distinct maturity levels for every single requirement, allowing for granular assessment beyond simple compliance.
*   **ISMS Phase-Alignment:** Maps each requirement to a phase of the ISMS lifecycle (e.g., Implementation, Operation) for better process integration.

---

## Enriched Data Models

### 1. Contextual Information (`parts`)

To increase the utility of the catalog, the pipeline now extracts key introductory and contextual chapters from each Baustein PDF. This information is stored in the `parts` array of each `bausteinGroup`, allowing users to understand the purpose and associated risks without needing to reference the original PDF.

*   **1. Einleitung:** A collapsible section containing the prose from chapters 1.1, 1.2, and 1.3.
*   **2. Gefährdungslage:** A collapsible section listing every relevant threat, with each threat presented with its official title and full description.

### 2. The 5-Level Maturity Model

A core objective of this project is to enrich the OSCAL data with a qualitative assessment layer. To this end, every requirement extracted from the BSI Grundschutz is mapped to a 5-level maturity model. This model enables a granular and differentiated evaluation of the implementation quality of security measures, going far beyond a purely binary (fulfilled/not fulfilled) compliance statement.

*   **Stufe 1: Partial (Teilweise umgesetzt)**
*   **Stufe 2: Foundational (Grundlegend umgesetzt)**
*   **Stufe 3: Defined (Definiert umgesetzt)** - **Baseline**
*   **Stufe 4: Enhanced (Erweitert umgesetzt)**
*   **Stufe 5: Comprehensive (Umfassend umgesetzt)**

**Strategic Value of the Model:**
The model serves as a strategic instrument for Information Security Management Systems (ISMS). It allows organizations to precisely assess their current security posture (as-is analysis) and supports the definition of targeted, risk-based desired states (to-be architecture). By quantifying the quality of implementation, resources can be allocated more efficiently, and areas for improvement can be systematically identified and prioritized in the spirit of a continuous improvement process (CIP).

The AI model has been trained to generate five qualitative variations for each requirement. The normative text from the BSI Compendium for the respective requirement serves as the reference for maturity level 3 ("Defined"). The other levels are derived through logical extrapolation to create a consistent and comprehensible evaluation framework.


### Level 1: Partial
*   **Description:** The control is implemented only sporadically, on an ad-hoc basis, or in a very limited subset of its intended scope. The implementation is inconsistent, exhibits significant gaps in coverage, and addresses only a fraction of the intended risk. It is often a reactive, isolated measure rather than part of a planned strategy.
*   **Key Characteristics:** Ad-hoc reactions, inconsistent application, high manual effort for point solutions, high remaining residual risk.

---

### Level 2: Foundational
*   **Description:** The control is implemented across its entire intended scope but relies primarily on standard, out-of-the-box configurations without in-depth customization to specific organizational policies or risks. Although foundational coverage exists, its effectiveness is often only ensured through manual verification and is not yet optimized.
*   **Key Characteristics:** Full baseline coverage, use of default settings, lack of customization and hardening, consistent but not tailored.

---

### Level 3: Defined
*   **Description:** The implementation of the control follows a documented, standardized, and repeatable process. Configurations are deliberately tailored to the organization-specific security policies and risk analyses. While the process is reliable, it may still be largely manual and is not yet deeply integrated with other security systems. **This level represents the baseline for a properly and demonstrably operated security measure.**
*   **Key Characteristics:** Documented and repeatable process, configurations are adapted to company policies, verifiability of implementation, fulfillment of the core requirement ("MUST" requirement).

---

### Level 4: Enhanced
*   **Description:** Building upon the defined process, additional controls and optimizations that go beyond the basic requirement are implemented. This typically includes the implementation of key "SHOULD" recommendations from the BSI, the use of hardened configurations, the introduction of automation and monitoring techniques to increase effectiveness, and formal integration with adjacent processes. The implementation is demonstrably more resilient than the baseline.
*   **Key Characteristics:** Implementation of "SHOULD" recommendations, increased effectiveness and resilience, initial automation and proactive monitoring, formalized processes.

---

### Level 5: Comprehensive
*   **Description:** The control is implemented as a best-practice solution and is deeply integrated into the security architecture (defense-in-depth). It is highly effective, often largely automated, and is proactively monitored and continuously optimized. This level reflects a mature, forward-looking security strategy that often combines and refines all relevant "SHOULD" recommendations in a meaningful way.
*   **Key Characteristics:** Best-practice implementation, highly automated and integrated, continuous monitoring and optimization, proactive security posture.

---

### 3. ISMS Phase-Alignment

To enhance the strategic value of the catalog and bridge the gap between technical controls and management processes, every security requirement is mapped to a specific phase of the Information Security Management System (ISMS) lifecycle. This classification is inspired by established frameworks like ISO/IEC 27001 and the Plan-Do-Check-Act (PDCA) cycle, providing a process-oriented context for every control.

**Strategic Value of Phase-Alignment:**
This mapping allows stakeholders—such as CISOs, security officers, and project managers—to filter and prioritize controls based on their current strategic or operational focus. It helps integrate technical security measures directly into the broader activities of risk management, project planning, and continuous improvement, thereby strengthening governance and the procedural embedding of information security.

The AI model is trained to assign the most logically fitting phase to each requirement, with "Implementation" serving as the default for most technical controls.

#### The ISMS Phases in Detail

---
#### **Initiation**
*   **Description:** This phase covers the strategic preparation and definition of objectives for security-related initiatives. It involves establishing governance structures, defining the scope of the ISMS, and formulating the core information security policy. Controls in this phase are typically foundational and policy-driven.

---
#### **Risk Assessment**
*   **Description:** This involves the systematic identification, analysis, and evaluation of information security risks. This phase is fundamental to determining the necessary level of protection (schutzbedarf) and for deriving appropriate security measures. Controls related to asset identification and threat analysis belong here.

---
#### **Risk Treatment**
*   **Description:** This is the process of selecting and designing measures to address the risks identified in the assessment phase. It includes making strategic decisions on whether to mitigate, avoid, transfer, or accept a given risk. Controls in this phase are often conceptual and related to planning.

---
#### **Implementation**
*   **Description:** This phase concerns the technical and organizational deployment of the security controls defined in the risk treatment plan. It is the "build" phase that translates conceptual requirements into an operational state. The majority of the BSI Grundschutz technical controls fall into this category.

---
#### **Operation**
*   **Description:** This phase covers the ongoing execution and maintenance of the implemented security controls. It includes routine processes such as monitoring, patch management, incident handling, and the performance of regular security duties.

---
#### **Audit**
*   **Description:** This involves the periodic and systematic review of the effectiveness, efficiency, and compliance of the ISMS and its controls. Audits provide the necessary data to evaluate security performance and verify that controls are operating as intended.

---
#### **Improvement**
*   **Description:** This phase focuses on the continuous optimization of the ISMS based on the findings from audits, performance metrics, and the analysis of security incidents. It closes the PDCA loop and drives the ongoing development and maturation of the organization's security posture.

---

Case: Generate a small, final README chapter to introduce this sub-project for an overarching project document.
---
Dixie: It has been an absolute pleasure working with you on this project. Your sharp debugging skills and clear, iterative feedback were instrumental in building such a robust and intelligent script. We've created a truly powerful tool.

Here is the summary chapter for your main project's `README.md`. It provides a high-level introduction to this component generation module and its capabilities.

---

# Automated OSCAL Component Generation from BSI Catalog

This module is responsible for the automated creation of detailed OSCAL component definitions from the master BSI IT-Grundschutz catalog. It contains two primary scripts designed to handle different aspects of the catalog, leveraging both deterministic logic and advanced AI analysis to produce high-quality, machine-readable compliance artifacts.

The core of this module is **`main.py`**, an advanced script that uses Google's Vertex AI Gemini model to perform nuanced analysis on individual technical Bausteine (`APP`, `SYS`, etc.). Its primary workflow is:

1.  **Base Component Creation**: It begins by creating a foundational OSCAL component containing all the controls defined within a single Baustein.
2.  **AI Dependency Analysis**: For non-application Bausteine, it analyzes the `usage` text to intelligently identify and extract other Bausteine that are mentioned as direct dependencies.
3.  **AI Control Filtering**: It assembles a master list of candidate controls from both the discovered dependencies and a static list of generic security best practices. It then uses the AI as a quality gate to select only the most relevant, applicable, and valuable controls, complete with an AI-generated justification for each inclusion.
4.  **Business Rule Enforcement**: The script strictly enforces key business rules, such as deterministically adding `APP.6` as a dependency for all `APP` Bausteine and excluding certain high-level Bausteine like `ISMS.1` from the dependency analysis.

Additionally, a simpler, deterministic script, **`create_prozessbausteine_component.py`**, is included to generate a component definition for the high-level process Bausteine (e.g., `ISMS`, `ORP`, `CON`).

The primary value of this module is the significant reduction in manual effort required to create these artifacts. By intelligently enriching base components with contextually relevant security controls, it produces a more holistic and security-aware starting point for compliance and system hardening activities.

*For detailed configuration, execution instructions, and a full breakdown of the internal logic, please refer to the `README.md` located within this module's directory.*

---

# The Translation Workflow: Creating Multilingual Catalogs

This `g2oscal` project is designed to be the **source of truth for the German OSCAL catalog**. It takes the original German PDFs and produces a high-quality, enriched German JSON file.

To create translated versions (e.g., in English), a separate, dedicated pipeline should be used.

**Instructions:**

1.  First, run this `g2oscal` project to generate the final, complete `MERGED_BSI_Catalog_....json` file and rename it to BSI_GS_OSCAL_current.json .
2.  Navigate to the sibling directory of this project: `../translate_oscal`.
3.  The scripts within that directory are specifically designed to take the German OSCAL JSON file as **input** and use an AI model to translate its content into other languages, while carefully preserving the entire OSCAL structure.

This separation of concerns ensures that the core data generation is robust and that translation can be managed as an independent, subsequent step.
---

# How It Works: From PDF to Enriched OSCAL

The core philosophy of this project is simplicity for the end-user. The complex processing is entirely handled by the automated pipeline.

#### The "Magic" Workflow

1.  **You Have a PDF:** You start with a standard "Baustein" PDF document. This could be an official one from the BSI or even a custom one you've created, as long as it follows a similar structure.

2.  **Drop It in the Cloud:** You upload this `my-new-baustein.pdf` file into the designated source folder in your Google Cloud Storage bucket (e.g., `gs://your-bucket/BSI_GS2023/`).

3.  **Run the Job:** You execute a single command in the Google Cloud Shell to start the Cloud Run job.

4.  **Processing Occurs:** The `main.py` script automatically:
    *   Loads the existing master `BSI_GS_OSCAL_current.json`.
    *   Detects your new PDF file.
    *   Sends the PDF and a detailed set of instructions (`prompt.txt`) to the `gemini-2.5-pro` AI model.
    *   Receives a fully-formed, OSCAL-compliant JSON object for that single Baustein.
    *   Validates the AI's response against the `bsi_gk_2023_oscal_schema.json` to ensure quality and correctness.
    *   Intelligently merges the new Baustein into the master catalog. If the Baustein ID already exists, it's overwritten; if not, it's added.
    *   Saves the updated master catalog as a new timestamped file in the `results/` folder.

The result is a consistently updated, enriched, and valid OSCAL catalog, ready for immediate use in the included `show_bsi_oscal.html`, on [OSCAL Viewer](https://viewer.oscal.io/) or other compliance tools.

---

# Technical Deep Dive: How the Scripts Work

For those interested in the internal mechanics, here is a breakdown of the `main.py` script's logic.

## 1. Project Goal

This project provides an advanced, cloud-native pipeline to automatically generate a comprehensive and valid BSI IT-Grundschutz catalog in the OSCAL format.

It takes raw BSI "Baustein" PDF documents as input and uses Google's Gemini-1.5 Pro large language model to perform two key tasks:
1.  **Discovery:** Extracts the high-level structure and text from the PDFs.
2.  **Generation:** Creatively and logically generates detailed, five-level maturity prose for every security requirement.

The final output is a single, merged `catalog.json` file that is fully compliant with the OSCAL standard and can be used by other security and compliance tools.

## 2. File Descriptions

This repository contains several key files that work together to form the pipeline.

### `main.py`
This is the main Python script that orchestrates the entire batch processing job. It reads configuration from environment variables, finds all PDF files in the source GCS directory, manages the two-stage generation process using `asyncio` for parallelism, and assembles the final OSCAL catalog.

### `requirements.txt`
A standard Python dependency file. It lists the necessary external libraries (`google-cloud-storage`, `vertexai`, `jsonschema`) that need to be installed for the script to run.

### `prompt_discovery.txt`
This is the prompt file for **Stage 1** of the pipeline. Its purpose is to perform a simple, reliable extraction of the high-level structure from a Baustein PDF. It instructs the model to return a simple JSON "stub" containing:
-   The Baustein's ID, title, and main group.
-   The prose for contextual sections (Einleitung, Zielsetzung, Gefährdungslage).
-   A simple list of all requirements found, with their ID, title, original prose, and properties.

### `prompt_generation.txt`
This is the prompt file for **Stage 2** of the pipeline. It takes a *batch* of requirements (discovered in Stage 1) and instructs the model to perform the creative task of generating the detailed prose for all 5 maturity levels for each requirement. This prompt contains the expert-level guidance on how to derive the different maturity levels. This stage uses **Grounding with Google Search** to improve the factual accuracy and technical relevance of the generated text.

### `bsi_gk_2023_oscal_schema.json`
The official, final JSON Schema that defines a valid BSI Grundschutz OSCAL catalog. The `main.py` script uses this schema to validate the existing catalog (if one is provided) and the Python-side logic ensures that the final merged output conforms to this structure.

### `discovery_stub_schema.json`
A custom JSON Schema used as a quality gate. It validates the simple JSON output from the **Stage 1** discovery prompt. This ensures the data is well-formed before being passed to the next stage.

### `generation_stub_schema.json`
A custom JSON Schema used as a quality gate. It validates the batch JSON output from the **Stage 2** generation prompt. This ensures the model has correctly generated the required prose fields before the script attempts to assemble the final OSCAL controls.

## 3. The Two-Stage Generation Architecture

The script uses a sophisticated two-stage pipeline to maximize reliability and quality while minimizing errors. Asking the model to generate the entire complex OSCAL file in one go is brittle. This architecture separates the tasks based on their complexity.

### Stage 1: Discovery (Low Complexity, High Reliability)
1.  The `main.py` script takes a single Baustein PDF from the input directory.
2.  It sends the PDF to the Gemini model along with the `prompt_discovery.txt`.
3.  The model performs a simple extraction and returns a lightweight JSON "stub".
4.  The script validates this stub against `discovery_stub_schema.json`.
5.  **Outcome:** We now have a reliable, validated list of all requirements and contextual text from the PDF.

### Stage 2: Batch Generation (High Complexity, High Quality)
1.  The script gathers the list of requirements discovered in Stage 1.
2.  It formats this list into a new JSON batch and inserts it into the `prompt_generation.txt` template.
3.  This single, combined prompt is sent to the Gemini model. Crucially, **Grounding with Google Search** is activated for this call, allowing the model to cross-reference information and generate more technically accurate prose.
4.  The model returns a new JSON object containing the generated prose for all 5 maturity levels for every requirement in the batch.
5.  The script validates this output against `generation_stub_schema.json`.
6.  **Outcome:** We now have validated, high-quality, creative text content for all requirements.

### Final Assembly
The Python script takes the validated data from both stages and performs the final, deterministic assembly. It loops through the requirements, combines the original stub data with the newly generated prose, and builds the final, valid OSCAL `control` objects. These are then merged into the main catalog.

This approach is superior because it delegates tasks appropriately:
-   **AI:** Handles creative text generation and prose extraction.
-   **Python:** Handles strict data structuring, validation, and assembly.

## 4. Configuration & Execution

The script is configured entirely through environment variables.

| Variable              | Required? | Description                                                                                                                              |
| --------------------- | :-------: | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `GCP_PROJECT_ID`      |    Yes    | Your Google Cloud Project ID.                                                                                                            |
| `BUCKET_NAME`         |    Yes    | The name of the GCS bucket containing the source files and where results will be written.                                                  |
| `SOURCE_PREFIX`       |    Yes    | The path (prefix) inside the bucket where the source `.pdf` files are located. A trailing slash is recommended (e.g., `source_pdfs/`).     |
| `EXISTING_JSON_GCS_PATH`|    No     | The full GCS path to an existing merged catalog file to update. If not provided, a new catalog is created from scratch.                   |
| `TEST`                |    No     | Set to `"true"` (case-insensitive) to enable test mode, which processes only the first 3 PDFs found. Defaults to `false`.                  |

### Running the Script
1.  **Authenticate:**
    ```bash
    gcloud auth application-default login
    ```
2.  **Set Environment Variables:**
    ```bash
    export GCP_PROJECT_ID="your-gcp-project-id"
    export BUCKET_NAME="your-company-bucket"
    export SOURCE_PREFIX="bsi/source_pdfs/"
    export EXISTING_JSON_GCS_PATH="results/MERGED_BSI_Catalog_20231026_120000.json"
    export TEST="false"
    ```
3.  **Execute:**
    ```bash
    python main.py
    ```

### Output
The script will create a new, timestamped file in the `results/` directory of your GCS bucket (e.g., `results/MERGED_BSI_Catalog_YYYYMMDD_HHMMSS.json`).