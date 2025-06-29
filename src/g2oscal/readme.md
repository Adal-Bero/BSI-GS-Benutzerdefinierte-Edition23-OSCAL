
# BSI-Grundschutz zu angereichertem OSCAL: Die automatische Konvertierungs-Pipeline

Dieses Projekt stellt eine leistungsstarke, automatisierte Pipeline zur Verfügung, um "Baustein"-PDF-Dokumente des BSI-Grundschutzes in ein reichhaltiges, strukturiertes und OSCAL-konformes JSON-Format zu konvertieren. Es nutzt die fortschrittlichen Fähigkeiten des `gemini-2.5-pro`-Modells von Google, um Inhalte nicht nur zu extrahieren, sondern sie auch tiefgehend mit einem mehrstufigen Reifegradmodell, Praxis-Klassifizierungen und anderen wichtigen Metadaten anzureichern. Dadurch wird der finale Katalog sofort für Analysen und das Compliance-Management nutzbar.

Das System ist für den Betrieb als serverloser **Google Cloud Run Job** konzipiert und arbeitet **inkrementell**. Es liest intelligent einen bestehenden OSCAL-Gesamtkatalog, verarbeitet neue oder aktualisierte PDFs und fügt die Ergebnisse nahtlos zusammen, indem es neue "Bausteine" hinzufügt oder bestehende überschreibt.

### Hauptfunktionen

*   **Vollautomatische Konvertierung:** Wandelt rohe PDF-Inhalte ohne manuellen Eingriff in strukturiertes OSCAL-JSON um.
*   **Inkrementelle Updates:** Fügt neue Bausteine intelligent hinzu oder überschreibt bestehende in einer zentralen Katalogdatei, was den Prozess wiederholbar und effizient macht.
*   **Tiefgehende Anreicherung:** Die Pipeline extrahiert nicht nur Text, sondern reichert jedes Control an mit:
    *   **Einem 5-stufigen Reifegradmodell:** Generiert fünf unterschiedliche Reifegrade für jede einzelne Anforderung.
    *   **Praxis-Klassifizierung:** Ordnet jedes Control einer funktionalen Sicherheitspraxis zu (z. B. GOV, RISK, ARCH).
    *   **Control-Klasse:** Klassifiziert jedes Control als `Technical`, `Operational` oder `Management`.
    *   **CIA-Schutzbedarfsanalyse:** Stellt fest, ob ein Control primär die Vertraulichkeit, Integrität oder Verfügbarkeit betrifft.
    *   **ISMS-Phasen-Klassifizierung:** Ordnet jedes Control einer relevanten Phase des ISMS-Lebenszyklus zu (z. B. Implementation, Operation, Audit).
    *   **Anforderungsebene:** Extrahiert die BSI-eigene Anforderungsebene (Basis, Standard oder Erhöht) und bildet sie auf eine strukturierte Eigenschaft ab.
*   **Kontextinformationen:** Extrahiert einleitende Kapitel (Einleitung, Zielsetzung) und die gesamte Gefährdungslage in strukturierte `parts`, um wichtigen Kontext direkt im Katalog bereitzustellen.
*   **Robust & Modular:** Der Code ist logisch in Module für Konfiguration, GCS-Interaktion und KI-Verarbeitung getrennt und folgt modernen Best Practices.

## Projekt-Werkzeuge

Dieses Projekt enthält zwei eigenständige HTML-basierte Werkzeuge zur Verarbeitung von BSI-Grundschutz-Katalogen im OSCAL-Format. Jedes Werkzeug hat einen spezifischen Anwendungszweck.

### 1. BSI Grundschutz OSCAL Viewer (`show_bsi_oscal (10).html`)

Dieses Werkzeug dient der reinen Visualisierung und Analyse eines BSI-Grundschutz-Katalogs im OSCAL-Format. Es ist ein reines Lesewerkzeug zur Exploration der Katalogdaten.

**Hauptmerkmale:**
-   **Zwei Ansichtsmodi:**
    1.  **Strukturansicht:** Zeigt den Katalog hierarchisch nach *Layer → Baustein → Anforderung* an.
    2.  **Practice-Ansicht:** Gruppiert alle Anforderungen nach ihrer zugeordneten "Practice" (z.B. Governance, Risikomanagement).
-   **Interaktive Filter:** Ermöglicht das Filtern der Anforderungen nach Schutzbedarf und ISMS-Phase.
-   **Darstellungsoptionen:** Bietet eine erweiterbare Baumansicht für die Struktur sowie eine flache Liste aller Anforderungen.

**Anwendungsfall:** Nutzen Sie diesen Viewer, wenn Sie einen OSCAL-Katalog explorieren, dessen Struktur verstehen oder schnell bestimmte Anforderungen anhand von Kriterien wie "Practice" oder Schutzbedarf finden möchten.

### 2. BSI Grundschutz OSCAL Checkliste (`WiBa_Checklisten_bsi_oscal (1).html`)

Dieses Werkzeug wandelt einen OSCAL-Katalog in eine interaktive Checkliste um, mit der der Umsetzungsstand von Anforderungen erfasst und gespeichert werden kann. Es ist für die aktive Bearbeitung und Dokumentation konzipiert.

**Hauptmerkmale:**
-   **Interaktive Formulare:** Rendert jede Anforderung als bearbeitbaren Checklisteneintrag.
-   **Dateneingabe:** Bietet Eingabefelder für Reifegrad, Umsetzungsstatus (z.B. implementiert, geplant) und individuelle Bemerkungen.
-   **Speichern & Laden:**
    -   Ermöglicht das **Speichern** der ausgefüllten Checkliste (inkl. Prüfername und Zeitstempel) als separate JSON-Ergebnisdatei.
    -   Ermöglicht das **Laden** einer zuvor gespeicherten Ergebnisdatei, um die Arbeit fortzusetzen.
-   **Visuelle Unterstützung:** Stellt die Reifegrade in einer farbkodierten Tabelle (von Rot nach Grün) dar, um eine schnelle visuelle Erfassung zu ermöglichen.

**Anwendungsfall:** Ideal für Audits, Gap-Analysen oder Selbstbewertungen. Nutzen Sie dieses Werkzeug, um den Status jeder Anforderung systematisch zu dokumentieren und Ihre Ergebnisse für die weitere Verwendung oder spätere Bearbeitung zu sichern.

---

## Die Zwei-Stufen-KI-Architektur

Um sowohl Zuverlässigkeit als auch Effizienz zu maximieren, verwendet diese Pipeline eine ausgeklügelte Zwei-Stufen-Architektur, die Aufgaben nach ihrer Komplexität delegiert. Dies ist eine Weiterentwicklung eines früheren Drei-Stufen-Modells, bei dem Extraktion und Klassifizierung in einem einzigen, effizienten ersten Schritt kombiniert werden.

```
+------------------+
| Baustein-PDF     |
| (in GCS)         |
+--------+---------+
         |
         v
+------------------------------------------+
|  STUFE 1: ERKENNUNG & ANREICHERUNG         |
| (Extraktions- + Klassifizierungs-KI)     |
+------------------+-----------------------+
                   |
                   v
+------------------------------------------+
| Validiertes & ANGEREICHERTES             |
|       Anforderungs-Stub-JSON             |
+------------------+-----------------------+
                   |
                   v
+------------------------------------------+
|      STUFE 2: GENERIERUNG                |
|    (Kreative Reifegrad-Prosa-KI)         |
+------------------+-----------------------+
                   |
                   v
    +--------------------------------------+
    | Validiertes Prosa-JSON (für alle     |
    |      5 Reifegrade)                   |
    +--------------+-----------------------+
                   |
                   v
   +---------------------------------------+
   |    PYTHON FINALE ASSEMBLIERUNG        |
   |  (Deterministische Strukturierung)   |
   +---------------+-----------------------+
                   |
                   v
     +-----------------------------------+
     |  Finales validiertes OSCAL-JSON   |
     +-----------------------------------+

```

### Stufe 1: Erkennung & Anreicherung (Hohe Zuverlässigkeit & Effizienz)
Der Prozess beginnt, indem das rohe PDF mit einem leistungsstarken, kombinierten Prompt (`prompt_discovery_enrichment.txt`) an die KI gesendet wird. Die Aufgabe der KI ist es, sowohl die Extraktion als auch die Klassifizierung in einem einzigen Aufruf durchzuführen:
1.  **Extrahieren:** Sie liest die Baustein-ID, Titel, kontextbezogene Teile und die Liste der Anforderungen mit ihrem Originaltext.
2.  **Anreichern:** Für jede extrahierte Anforderung klassifiziert sie *sofort* deren `practice`, `class`, `CIA`-Auswirkung, ISMS-`phase` und `level`.
Die kombinierte JSON-Ausgabe wird gegen das strikte `discovery_enrichment_stub_schema.json` validiert.

### Stufe 2: Generierung (Hohe Qualität, Kreativ)
Die angereicherte Liste der Anforderungen aus Stufe 1 wird dann an den zweiten KI-Aufruf übergeben. Mithilfe des `prompt_generation.txt` übernimmt die KI die komplexe, kreative Arbeit, die detaillierte Prosa für alle 5 Reifegrade für den gesamten Stapel von Anforderungen zu schreiben. Das Ergebnis wird gegen `generation_stub_schema.json` validiert.

### Finale Assemblierung (Deterministisch)
Das Python-Skript (`main.py`) fungiert als finaler, deterministischer Assemblierer. Es sammelt die validierten Daten aus beiden Stufen und erstellt die endgültigen, vollständigen OSCAL-`control`-Objekte. Diese werden in den Hauptkatalog zusammengeführt, der dann ein letztes Mal gegen das Master-Schema `bsi_gk_2023_oscal_schema.json` validiert wird, bevor er gespeichert wird.

---

## Dateibeschreibungen

### Kernlogik
*   **`main.py`:** Der Haupt-Orchestrator. Er liest die Konfiguration, findet Dateien, verwaltet die `asyncio`-Event-Loop für die parallele Verarbeitung, ruft die Utility-Module auf und stellt den finalen OSCAL-Katalog zusammen.
*   **`config.py`:** Ein zentraler Hub für die gesamte Konfiguration. Er lädt Umgebungsvariablen, definiert statische Dateipfade und Wiederholungseinstellungen und richtet den Logger ein.
*   **`gcs_utils.py`:** Ein dediziertes Modul für alle Interaktionen mit Google Cloud Storage (Auflisten, Lesen, Schreiben von Dateien).
*   **`gemini_utils.py`:** Das "KI-Gehirn" des Projekts. Es initialisiert das Gemini-Modell und enthält die Kernlogik für die Zwei-Stufen-KI-Verarbeitungspipeline, einschließlich der in sich geschlossenen Wiederholungsschleifen für jeden API-Aufruf.

### Prompts
*   **`prompt_discovery_enrichment.txt`:** Dieser einzelne, leistungsstarke Prompt weist die KI an, sowohl die strukturelle Extraktion als auch die detaillierte Klassifizierung (practice, class, CIA, phase, level) in einem effizienten Schritt durchzuführen.
*   **`prompt_generation.txt`:** Ein detaillierter Experten-Prompt, der die KI bei der kreativen Aufgabe anleitet, die Prosa für die 5 Reifegrade zu schreiben.

### Schemas (Qualitäts-Gates)
*   **`bsi_gk_2023_oscal_schema.json`:** Das finale, strikte JSON-Schema, das einen gültigen BSI-Grundschutz-OSCAL-Katalog definiert. Es wird verwendet, um die endgültige Ausgabe vor dem Speichern zu validieren.
*   **`discovery_enrichment_stub_schema.json`:** Validiert die kombinierte Ausgabe der Erkennungs- & Anreicherungs-Stufe.
*   **`generation_stub_schema.json`:** Validiert die Ausgabe der Generierungs-Stufe.

### Andere Dateien
*   **`requirements.txt`:** Listet alle notwendigen Python-Bibliotheken auf.
*   **`Dockerfile`:** Definiert das Container-Image für das Deployment auf Google Cloud Run.

---
## Angereicherte Datenmodelle

### 1. Das 5-stufige Reifegradmodell
Jede aus dem BSI-Grundschutz extrahierte Anforderung wird einem 5-stufigen Reifegradmodell zugeordnet, was eine granulare Bewertung der Umsetzungsqualität ermöglicht.
*   **Stufe 1: Partial (Teilweise umgesetzt)**
*   **Stufe 2: Foundational (Grundlegend umgesetzt)**
*   **Stufe 3: Defined (Definiert umgesetzt)** - **Basislinie**
*   **Stufe 4: Enhanced (Erweitert umgesetzt)**
*   **Stufe 5: Comprehensive (Umfassend umgesetzt)**

### 2. Praxis-Klassifizierung
Jedes Control wird einer funktionalen Praxis-Domäne zugeordnet, wie z.B. `GOV` (Governance), `RISK` (Risikomanagement) oder `SYS` (Systemschutz). Dies ermöglicht eine rollen- oder funktionsbasierte Sicht auf die Sicherheitsmaßnahmen.

### 3. Control-Klasse & CIA-Schutzziele
*   **Klasse:** Jedes Control wird gemäß dem NIST-Standard als `Technical`, `Operational` oder `Management` klassifiziert, was die Art der Implementierung verdeutlicht.
*   **CIA:** Jedes Control wird mit Booleans (`effective_on_c`, `effective_on_i`, `effective_on_a`) versehen, um seine primäre Auswirkung auf Vertraulichkeit (Confidentiality), Integrität (Integrity) und Verfügbarkeit (Availability) zu zeigen.

### 4. ISMS-Phase & Anforderungsebene
*   **ISMS-Phase:** Jedes Control wird mit seiner relevantesten ISMS-Lebenszyklusphase (z. B. `Implementation`, `Operation`, `Audit`) versehen, um Kontext zu liefern, wann die Maßnahme zu berücksichtigen ist.
*   **Anforderungsebene:** Die ursprüngliche BSI-Ebene – `Basis-Anforderung` (Level 1), `Standard-Anforderung` (Level 3) oder `Anforderung bei erhöhtem Schutzbedarf` (Level 5) – wird extrahiert und als separate Eigenschaft gespeichert. Dies bewahrt die BSI-eigene Klassifizierung, getrennt vom generierten 5-stufigen Reifegradmodell.

---

## Konfiguration & Lokale Ausführung

Das Skript wird vollständig über Umgebungsvariablen konfiguriert.

| Variable                 | Erforderlich? | Beschreibung                                                                                                                             |
| ------------------------ | :-----------: | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `GCP_PROJECT_ID`         |      Ja       | Ihre Google Cloud Projekt-ID.                                                                                                            |
| `BUCKET_NAME`            |      Ja       | Der Name des GCS-Buckets, der die Quelldateien enthält und in den die Ergebnisse geschrieben werden.                                     |
| `SOURCE_PREFIX`          |      Ja       | Der Pfad (Präfix) innerhalb des Buckets, in dem sich die `.pdf`-Quelldateien befinden. Ein abschließender Schrägstrich wird empfohlen (z. B. `source_pdfs/`). |
| `EXISTING_JSON_GCS_PATH` |      Nein     | Der vollständige GCS-Pfad zu einer bestehenden Katalogdatei, die aktualisiert werden soll. Wenn nicht angegeben, wird ein neuer Katalog erstellt. |
| `TEST`                   |      Nein     | Setzen Sie dies auf `"true"`, um den Testmodus zu aktivieren (Groß- und Kleinschreibung wird nicht beachtet). Dieser verarbeitet nur die ersten 3 PDFs und nur 10 % der Anforderungen in jeder Datei. |


### Lokale Ausführung
1.  **Authentifizieren Sie sich bei Google Cloud:**
    ```bash
    gcloud auth application-default login
    ```
2.  **Setzen Sie die Umgebungsvariablen (Beispiel):**
    ```bash
    export GCP_PROJECT_ID="your-gcp-project-id"
    export BUCKET_NAME="your-company-bucket"
    export SOURCE_PREFIX="bsi/source_pdfs/"
    export EXISTING_JSON_GCS_PATH="results/MERGED_BSI_Catalog_latest.json"
    export TEST="false"
    ```
3.  **Installieren Sie die Abhängigkeiten und führen Sie das Skript aus:**
    ```bash
    pip install -r requirements.txt
    python main.py
    ```

---

## Deployment auf Google Cloud Run Jobs

Diese Anwendung ist für den Betrieb als serverloser Batch-Job konzipiert.

### Schritt 1: Erstellen Sie das Container-Image
Verwenden Sie Google Cloud Build, um ein Container-Image aus dem `Dockerfile` zu erstellen und es in die Artifact Registry zu pushen.

```bash
gcloud builds submit --tag gcr.io/[YOUR_PROJECT_ID]/g2oscal-pipeline .
```

### Schritt 2: Erstellen Sie den Cloud Run Job
Erstellen Sie einen Job, der das Container-Image verwendet und die notwendigen Umgebungsvariablen übergibt.

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
> **Hinweis:** Stellen Sie sicher, dass das vom Job verwendete Servicekonto die Rollen "Vertex AI User" und "Storage Object Admin" besitzt.

### Schritt 3: Führen Sie den Job aus
Sie können den Job manuell über die Konsole oder über die Kommandozeile ausführen.

```bash
gcloud run jobs execute g2oscal-job --region [YOUR_GCP_REGION]
```
Der Job wird ausgeführt, verarbeitet alle neuen PDFs, fügt sie dem Katalog hinzu und speichert die neue Version in Google Cloud Storage.
```