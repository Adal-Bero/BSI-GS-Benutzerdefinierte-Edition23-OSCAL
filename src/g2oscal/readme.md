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
 
he pipeline uses a sophisticated multi-stage approach to maximize reliability and quality. Instead of a single, monolithic request, the work is broken down into logical, parallelizable steps.

A.  **Stage 1: Discovery**
    *   The script sends the raw PDF to the AI with a focused prompt (`prompt_discovery.txt`) to extract only the high-level structure: the Baustein ID, titles, contextual parts, and a simple list of all requirements with their original text.

B.  **Stage 2 & 3: Parallel Generation & Enrichment**
    *   Once the requirements list is discovered, the script launches two AI tasks *in parallel*:
        *   **Generation Task:** Uses `prompt_generation.txt` to perform the complex, creative work of writing the prose for all 5 maturity levels for the entire batch of requirements.
        *   **Enrichment Task:** Uses `prompt_enrichment.txt` to perform the analytical work of classifying each requirement's `practice`, `class`, and CIA impact.

C.  **Final Assembly**
    *   The Python script acts as the final assembler. It gathers the structured data from all three stages and deterministically builds the final, valid OSCAL JSON objects, ensuring perfect structure and compliance with the final schema.

The result is a consistently updated, enriched, and valid OSCAL catalog, ready for immediate use in the included `show_bsi_oscal.html`, on [OSCAL Viewer](https://viewer.oscal.io/) or other compliance tools.