# BSI Grundschutz to OSCAL: The Automated Conversion Pipeline

This project provides a powerful, automated pipeline for converting BSI Grundschutz "Baustein" PDF documents into a rich, structured, and OSCAL-compliant JSON format. It leverages the advanced capabilities of Google's `gemini-2.5-pro` model to not only translate the content but to enrich it with a multi-level maturity model and contextual information, making the final catalog immediately useful for analysis and compliance management.

The system is designed to run as a serverless **Google Cloud Run Job** and operates **incrementally**. It intelligently reads an existing master OSCAL catalog, processes new or updated PDFs, and seamlessly merges the results by adding new "Bausteine" or overwriting existing ones.

### Key Features

*   **Fully Automated Conversion:** Transforms raw PDF content into structured OSCAL JSON with zero manual intervention.
*   **Incremental Updates:** Intelligently adds new Bausteine or overwrites existing ones in a master catalog file, making the process repeatable and efficient.
*   **Contextual Enrichment:** Extracts introductory chapters (Einleitung, Zielsetzung, Modellierung) and the complete threat landscape (Gefährdungslage) into structured `parts`, providing vital context directly within the catalog.
*   **G++ conformant Practices** Each control will be sorted into one of the defined practices.
*   **OSCAL Compliant Controls Classes** Each control will be assigned a class based on the official OSCAL specification.
*   **BSI Level** Each control be get a level based on the BSI GRundschutz Categories Basis, STandard und Erhöht in the new G++ conformant level 1 to 5
*   **5-Level Maturity Model:** Generates five distinct maturity levels for every single requirement, allowing for granular assessment beyond simple compliance.
*   **ISMS Phase-Alignment:** Maps each requirement to a phase of the ISMS lifecycle (e.g., Implementation, Operation) for better process integration.

---

# Tools provided

## Automated OSCAL Component Generation from BSI Catalog

The `g2oscal` tool is designed to be the **an easy way to convert BSI GRundschutz Bausteine into German OSCAL catalog**. It takes the original German PDFs and produces a high-quality, enriched German JSON file.

---

## The Translation Workflow: Creating Multilingual Catalogs

To create translated versions (e.g., in English), `translate_oscal` can translate into any language that the genAI offers.

1.  First, run `g2oscal` project to generate a German OSCAL `BSI_Catalog_....json` file.
2.  Navigate to the sibling directory of this project: `../translate_oscal`.
3.  The scripts within that directory are specifically designed to take the German OSCAL JSON file as **input** and use an AI model to translate its content into other languages, while carefully preserving the entire OSCAL structure.

This separation of concerns ensures that the core data generation is robust and that translation can be managed as an independent, subsequent step.

---

## Create Component Definitions

Project `oscal_components_from_grundschutz` contains a script designed to automatically generate enriched OSCAL component definitions from a BSI IT-Grundschutz catalog. The script identifies individual "Bausteine" (building blocks) from the source catalog, creates a base component definition for each, and then uses the Google Vertex AI Gemini Pro model to intelligently discover and add relevant controls from other Bausteine. To generate the rather static component for the "Process Modules" / "Prozessbausteine" a smaller script exists as well: `create_prozessbausteine_component.py`. This is run once.

The final output is a set of OSCAL-compliant JSON files, one for each technical Baustein, saved to a Google Cloud Storage (GCS) bucket.

---

## Quality Assurance

The tool `quality_control` will take a OSCAL component definitions and a catalog and performs a sophisticated, multi-faceted quality control and enrichment cycle on an OSCAL-based security catalog. It goes beyond simple linting or syntax checks by using a large language model (Google Gemini 2.5 Pro) to analyze the semantic meaning, context, and completeness of security controls.

It will add comments to the catalog in a part called "prose_qs" and add new controls when the current set is not complete.


---

# Enriched Data Models

## 1. Contextual Information (`parts`)

To increase the utility of the catalog, the pipeline now extracts key introductory and contextual chapters from each Baustein PDF. This information is stored in the `parts` array of each `bausteinGroup`, allowing users to understand the purpose and associated risks without needing to reference the original PDF.

*   **1. Einleitung:** A collapsible section containing the prose from chapters 1.1, 1.2, and 1.3.
*   **2. Gefährdungslage:** A collapsible section listing every relevant threat, with each threat presented with its official title and full description.

## 2. The 5-Level Maturity Model

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

## 3. ISMS Phase-Alignment

To enhance the strategic value of the catalog and bridge the gap between technical controls and management processes, every security requirement is mapped to a specific phase of the Information Security Management System (ISMS) lifecycle. This classification is inspired by established frameworks like ISO/IEC 27001 and the Plan-Do-Check-Act (PDCA) cycle, providing a process-oriented context for every control.

**Strategic Value of Phase-Alignment:**
This mapping allows stakeholders—such as CISOs, security officers, and project managers—to filter and prioritize controls based on their current strategic or operational focus. It helps integrate technical security measures directly into the broader activities of risk management, project planning, and continuous improvement, thereby strengthening governance and the procedural embedding of information security.

The AI model is trained to assign the most logically fitting phase to each requirement, with "Implementation" serving as the default for most technical controls.

### The ISMS Phases in Detail

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

