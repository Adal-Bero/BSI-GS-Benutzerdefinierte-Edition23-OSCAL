Ich hab die letzten 24 Stunden diesen Code vibe coded und möchte den hier ablegen.

Eingabeformat ist PDF. Also wer einen eigenen Baustein als PDF hat, kann mit dem Code ein valides OSCAL erzeugen.

Wer mag kann auch von genAI ein PDF mit Anforderungen für ein beliebiges Thema erzeugen lassen und dass dann hier in den Code füttern. Oder gleich ein OSCAL erzeugen lassen. Das JSON Schema liegt ja auch hier.

Alle 111 Bausteine im OSCAL viewer:
![Alle 111 Bausteine im OSCAL viewer](https://github.com/Stand-der-Technik/Nutzergenerierte-Kataloge/blob/main/g2oscal/Screenshot%202025-06-17%20215128.png "Alle 111 Bausteine im OSCAL viewer")

---

# BSI Grundschutz zu OSCAL - Automatischer Konverter

Dieses Projekt enthält ein automatisiertes Skript, das PDF-Dokumente aus dem BSI Grundschutz-Kompendium verarbeitet und in ein strukturiertes, maschinenlesbares OSCAL-Format (JSON) umwandelt. Es nutzt Google's KI-Modell (Gemini), um die Inhalte der PDFs zu analysieren und in das Zielformat zu transformieren.

Das System ist als **Cloud Run Job** in der Google Cloud konzipiert. Das bedeutet, es ist eine Aufgabe, die bei Bedarf gestartet wird, alle gefundenen Dateien verarbeitet und sich dann automatisch wieder beendet.

---

### BSI-Grundschutz OSCAL Viewer

Dies ist eine in sich geschlossene HTML-Anwendung zum Parsen, Visualisieren und Filtern von BSI-Grundschutz-Katalogen, die dem bereitgestellten OSCAL-basierten JSON-Schema entsprechen. Um die Anwendung zu nutzen, öffnen Sie einfach die Datei `viewer.html` in einem modernen Webbrowser, fügen Sie Ihre JSON-Daten in das vorgesehene Textfeld ein und klicken Sie auf den Button "Katalog rendern". Der Viewer generiert daraufhin unmittelbar eine interaktive, ausklappbare Baumansicht Ihres gesamten Katalogs. Das Hauptmerkmal ist das leistungsstarke Filter-Panel, das es Ihnen ermöglicht, die Anforderungen anhand von drei zentralen, BSI-spezifischen Kriterien einzugrenzen: **Schutzbedarf**, **ISMS-Phase** und **Reifegrad**. Die Ergebnisse können in zwei verschiedenen Modi angezeigt werden: in einer **gefilterten Baumansicht**, die nur die passenden Anforderungen und deren übergeordnete Zweige anzeigt, oder in einer **flachen Listenansicht**, die alle passenden Anforderungen als einfache, scrollbare Liste von Karten darstellt. Dies ermöglicht eine schnelle Analyse und eine fokussierte Überprüfung spezifischer Anforderungen innerhalb eines großen Katalogs. Die gesamte Anwendung ist in einer einzigen Datei ohne externe Abhängigkeiten oder serverseitige Komponenten enthalten, was sie äußerst portabel und einfach zu bedienen macht.

## Projektübersicht

Das Projekt besteht aus drei Hauptkomponenten, die zusammenarbeiten:

1.  **`main.py` (Das "Gehirn" der Operation):**
    *   Dies ist das zentrale Python-Skript, das die gesamte Logik enthält.
    *   **Was es tut:** Es stellt eine Verbindung zur Google Cloud her, liest alle PDF-Dateien aus einem festgelegten Ordner im Cloud Storage, schickt jede einzelne Datei zusammen mit Anweisungen an das Gemini-KI-Modell und fügt die Ergebnisse am Ende zu einer einzigen, großen JSON-Datei zusammen.
    *   **Besonderheiten:** Das Skript ist robust gebaut. Wenn bei der Verarbeitung einer Datei ein Fehler auftritt (z.B. weil die KI eine fehlerhafte Antwort gibt), versucht es die Verarbeitung automatisch bis zu dreimal, bevor es die Datei überspringt. Dies stellt sicher, dass der gesamte Job nicht wegen eines einzelnen Problems abbricht.

2.  **`prompt.txt` (Die "Anleitung" für die KI):**
    *   Dies ist eine einfache Textdatei, die die detaillierten Anweisungen für das Gemini-KI-Modell enthält.
    *   **Was es tut:** Diese Datei ist wie ein sehr präziser Befehl an einen extrem fähigen, aber sehr detailorientierten Mitarbeiter. Sie erklärt der KI ganz genau, wie sie die Informationen aus dem BSI-PDF lesen, interpretieren und in das OSCAL-JSON-Format umwandeln soll. Jede Regel, von der Struktur der Ausgabe bis hin zur deutschen Sprache, ist hier festgelegt.
    *   **Wichtigkeit:** Die Qualität des Endergebnisses hängt direkt von der Präzision dieser Anweisungen ab. Eine kleine Änderung in dieser Datei kann das Verhalten der KI stark beeinflussen.

3.  **`bsi_gk_2023_oscal_schema.json` (Die "Blaupause" für die Ausgabe):**
    *   Diese Datei definiert die exakte Struktur, die die finale JSON-Datei haben muss. Sie ist wie ein Bauplan oder eine Vorlage.
    *   **Was es tut:** Die KI erhält nicht nur die textlichen Anweisungen aus der `prompt.txt`, sondern auch diese Schema-Datei. Sie nutzt diese Blaupause, um sicherzustellen, dass ihre Ausgabe perfekt strukturiert ist. Dies hilft, Fehler zu vermeiden und eine konsistente, valide JSON-Datei zu garantieren.
    *   **Wichtigkeit:** Dieses Schema ist die "Wahrheit" für die Struktur. Es stellt sicher, dass alle generierten Dateien dem gleichen Format folgen und von anderen Systemen korrekt gelesen werden können.

---

## Implementiertes Reifegradmodell

Ein Kernziel dieses Projekts ist die Anreicherung der OSCAL-Daten um eine qualitative Bewertungsebene. Zu diesem Zweck wird jede aus dem BSI Grundschutz extrahierte Anforderung einem 5-stufigen Reifegradmodell zugeordnet. Dieses Modell ermöglicht eine granulare und differenzierte Bewertung der Implementierungsqualität von Sicherheitsmaßnahmen und geht damit über eine rein binäre (erfüllt/nicht erfüllt) Konformitätsaussage hinaus.

**Strategischer Nutzen des Modells:**
Das Modell dient als strategisches Instrument für das Informationssicherheits-Management (ISMS). Es ermöglicht Organisationen eine präzise Standortbestimmung ihrer aktuellen Sicherheitslage (As-Is-Analyse) und unterstützt die Definition von zielgerichteten, risikobasierten Soll-Zuständen (To-Be-Architektur). Durch die Quantifizierung der Implementierungsqualität können Ressourcen effizienter allokiert und Verbesserungspotenziale im Sinne eines kontinuierlichen Verbesserungsprozesses (KVP) systematisch identifiziert und priorisiert werden.

Das KI-Modell wurde darauf trainiert, für jede Anforderung fünf qualitative Ausprägungen zu generieren. Der normative Text der jeweiligen Anforderung aus dem BSI-Kompendium dient dabei als Referenz für die Reifegradstufe 3 ("Defined"). Die weiteren Stufen werden durch logische Extrapolation abgeleitet, um ein konsistentes und nachvollziehbares Bewertungs-Framework zu schaffen.

**Definition der fünf Reifegradstufen:**

*   **Stufe 1: Partial (Teilweise umgesetzt)**
    *   **Beschreibung:** Die Maßnahme wird lediglich sporadisch, ad-hoc oder nur in einem begrenzten Teilbereich des Geltungsbereichs angewendet. Die Implementierung ist inkonsistent und weist signifikante Abdeckungslücken auf, wodurch das angestrebte Schutzniveau nicht erreicht wird.

*   **Stufe 2: Foundational (Grundlegend umgesetzt)**
    *   **Beschreibung:** Die Maßnahme ist im gesamten Geltungsbereich implementiert, jedoch primär auf Basis von Standardkonfigurationen und ohne spezifische Anpassung an organisationale Richtlinien. Obwohl eine flächendeckende Grundfunktion existiert, ist die Wirksamkeit oft nur durch manuelle Verifikation sichergestellt.

*   **Stufe 3: Defined (Definiert umgesetzt)**
    *   **Beschreibung:** Die Umsetzung der Maßnahme folgt einem dokumentierten, standardisierten und wiederholbaren Prozess. Die Konfigurationen sind bewusst an die unternehmensspezifischen Sicherheitsrichtlinien und Schutzbedarfsanalysen angepasst. Diese Stufe repräsentiert die **Baseline für eine ordnungsgemäß und nachweisbar betriebene Sicherheitsmaßnahme.**

*   **Stufe 4: Enhanced (Erweitert umgesetzt)**
    *   **Beschreibung:** Aufbauend auf dem definierten Prozess werden zusätzliche, über die Basisanforderung hinausgehende Kontrollen implementiert. Dies umfasst typischerweise die Umsetzung von "SOLLTE"-Empfehlungen des BSI, die Nutzung gehärteter Konfigurationen oder die Einführung von Automatisierungs- und Monitoring-Techniken zur Steigerung der Effektivität und Resilienz.

*   **Stufe 5: Comprehensive (Umfassend umgesetzt)**
    *   **Beschreibung:** Die Maßnahme ist als Best-Practice-Lösung implementiert und tief in die Sicherheitsarchitektur integriert (Defense-in-Depth). Sie ist hochgradig effektiv, oftmals weitgehend automatisiert und wird proaktiv überwacht und optimiert. Diese Stufe reflektiert eine ausgereifte, vorausschauende Sicherheitsstrategie.

---

## Zuordnung zu Phasen des ISMS-Lebenszyklus

In Anlehnung an etablierte Management-Frameworks wie ISO/IEC 27001 und den PDCA-Zyklus (Plan-Do-Check-Act) wird jede extrahierte Sicherheitsanforderung einer spezifischen Phase des ISMS-Lebenszyklus zugeordnet. Diese Klassifizierung dient der prozessorientierten Strukturierung der Kontrollen und erleichtert deren Integration in strategische und operative Managementprozesse.

**Strategischer Nutzen der Phasenzuordnung:**
Die Zuordnung ermöglicht es Verantwortlichen (z.B. CISO, ISB, Projektleiter), Sicherheitsanforderungen kontextbezogen zu filtern und zu priorisieren. Sie schafft eine Brücke zwischen technischen Einzelmaßnahmen und den übergeordneten Phasen des Risikomanagements und der Projektplanung, wodurch die Governance und die prozessuale Einbettung der Informationssicherheit gestärkt werden.

Das KI-Modell ist darauf trainiert, jeder Anforderung die logisch passendste Phase zuzuweisen, wobei "Implementation" als Standard für die meisten technischen Kontrollen dient.

**Die ISMS-Phasen im Detail:**

*   **Initiation (Initiierung):**
    *   **Beschreibung:** Umfasst die strategische Vorbereitung und Zieldefinition für sicherheitsrelevante Vorhaben. In dieser Phase werden Governance-Strukturen etabliert, der Geltungsbereich des ISMS definiert und die grundlegende Sicherheitspolitik formuliert.

*   **Risk Assessment (Risikobewertung):**
    *   **Beschreibung:** Systematische Identifikation, Analyse und Bewertung von Informationssicherheitsrisiken. Diese Phase ist fundamental für die Ermittlung des Schutzbedarfs und die Ableitung adäquater Maßnahmen.

*   **Risk Treatment (Risikobehandlung):**
    *   **Beschreibung:** Auswahl und Konzeption von Maßnahmen zur Mitigation der identifizierten Risiken. Dies beinhaltet die Entscheidung, Risiken zu reduzieren, zu vermeiden, zu transferieren oder bewusst zu akzeptieren.

*   **Implementation (Umsetzung):**
    *   **Beschreibung:** Die technische und organisatorische Implementierung der im Risikobehandlungsplan definierten Sicherheitsmaßnahmen (Controls). Diese Phase überführt die konzeptionellen Vorgaben in den operativen Zustand.

*   **Operation (Betrieb):**
    *   **Beschreibung:** Der laufende Betrieb und die Wartung der implementierten Sicherheitsmaßnahmen. Dies schließt Prozesse wie Monitoring, Patch-Management und die Durchführung regulärer Sicherheitsaufgaben ein.

*   **Audit (Prüfung/Revision):**
    *   **Beschreibung:** Die periodische und systematische Überprüfung der Wirksamkeit, Effizienz und Konformität des ISMS und seiner Kontrollen. Audits liefern die Datengrundlage für die Bewertung der Sicherheitsleistung.

*   **Improvement (Verbesserung):**
    *   **Beschreibung:** Die kontinuierliche Optimierung des ISMS basierend auf den Ergebnissen von Audits, Performance-Messungen und der Analyse von Sicherheitsvorfällen. Diese Phase schließt den PDCA-Zyklus und treibt die Weiterentwicklung des Sicherheitsniveaus an.


### Abgrenzung zu etablierten Reifegradmodellen (NIST CSF, CMMI)

Die Konzeption des hier verwendeten 5-stufigen Reifegradmodells erfolgte bewusst in Anlehnung an die grundlegenden Prinzipien etablierter Frameworks wie dem **NIST Cybersecurity Framework (CSF) Maturity Tiers** und dem **Capability Maturity Model Integration (CMMI)**. Dennoch wurde ein spezifisches, adaptiertes Modell entwickelt, da die etablierten Standards für den primären Anwendungszweck dieses Projekts – die qualitative Anreicherung eines **Anforderungskatalogs** – nur bedingt geeignet sind.

Die Überlegenheit des gewählten Ansatzes für diesen Kontext begründet sich in drei wesentlichen Unterscheidungsmerkmalen:

#### 1. Fokus: Kontroll-zentriert vs. Prozess- und Organisations-zentriert

*   **NIST CSF Tiers (Partial, Risk-Informed, Repeatable, Adaptive):** Diese Stufen bewerten die Maturität der **Risikomanagement-Prozesse** einer gesamten Organisation. Sie beantworten die Frage: "Wie ausgereift ist die Fähigkeit unserer Organisation, Cybersicherheitsrisiken zu managen?". Der Fokus liegt auf der strategischen und prozessualen Ebene.
*   **CMMI (Initial, Managed, Defined, etc.):** Dieses Modell bewertet die Maturität und Leistungsfähigkeit von **Prozessen** innerhalb einer Organisation (z.B. Softwareentwicklung). Es zielt auf die Optimierung, Messbarkeit und Vorhersagbarkeit von organisationsweiten Abläufen ab.
*   **Unser Modell (Partial, Foundational, Defined, etc.):** Dieses Modell ist bewusst **kontroll-zentriert**. Es bewertet nicht die Organisation oder ihre Prozesse, sondern die **technische Implementierungsqualität einer einzelnen, spezifischen Sicherheitsanforderung**. Es beantwortet die Frage: "Wie gut und umfassend ist die Anforderung APP.3.2.A1 'Sichere Konfiguration eines Webservers' bei uns umgesetzt?".

Diese granulare, auf die einzelne Maßnahme fokussierte Sichtweise ist für die Erstellung eines detaillierten, operativ nutzbaren OSCAL-Katalogs unerlässlich.

#### 2. Anwendungszweck: Deskriptiver Katalog vs. Organisatorisches Assessment

Die Modelle von NIST und CMMI sind primär **Assessment-Frameworks**. Sie werden eingesetzt, um den Ist-Zustand einer existierenden Organisation zu bewerten und einen Soll-Zustand zu definieren.

Das hier entwickelte Modell dient einem anderen Zweck: Es ist **deskriptiv** und darauf ausgelegt, einen Anforderungskatalog zu strukturieren. Es bietet dem Anwender für jede Anforderung ein "Menü" an möglichen Implementierungstiefen. Ein IT-Architekt oder Systemverantwortlicher kann so für ein neues System entscheiden: "Für diesen Dienst genügt eine 'Defined' (Stufe 3) Umsetzung, für jenen hochkritischen Dienst streben wir eine 'Comprehensive' (Stufe 5) Umsetzung an." Diese direkte Anwendbarkeit auf der Ebene der Lösungsarchitektur ist durch die organisationsweiten Modelle nicht gegeben.

#### 3. Zielgruppe und Umsetzbarkeit: Technische vs. Management-Ebene

Die Sprache und die Kriterien der etablierten Modelle richten sich primär an das Management, an Prozessverantwortliche und an Auditoren. Begriffe wie "Quantitatively Managed" (CMMI) oder "Adaptive" (NIST CSF) sind für die technische Umsetzungsebene abstrakt.

Unser Modell ist direkt auf die **technische Praxis** zugeschnitten. Die Unterscheidung zwischen "Defined" (Stufe 3) und "Enhanced" (Stufe 4) ist oft konkret an die Umsetzung von "MUSS"- vs. "SOLLTE"-Anforderungen aus dem BSI-Grundschutz gekoppelt. Dies schafft eine unmittelbare, nachvollziehbare und umsetzbare Anleitung für Administratoren und Entwickler.

### Zusammenfassende Gegenüberstellung

| Kriterium | Unser Modell | NIST CSF Tiers | CMMI |
| :--- | :--- | :--- | :--- |
| **Primärer Fokus** | Qualität einer **einzelnen Sicherheitsmaßnahme** | Risikomanagement-Prozesse einer **Organisation** | Prozessfähigkeit einer **Organisation** |
| **Anwendungsziel** | Anreicherung eines **Anforderungskatalogs**, Lösungsdesign | **Assessment** des organisatorischen ISMS-Reifegrads | **Prozessverbesserung** und -bewertung |
| **Granularität** | Hoch (pro Kontrolle) | Niedrig (organisationsweit) | Mittel bis niedrig (prozessweit) |
| **Primäre Zielgruppe**| Technische Teams, Architekten, Systemverantwortliche | C-Level Management, CISO, Risikomanager | Prozess-Owner, Qualitätsmanagement, Auditoren |

Zusammenfassend lässt sich sagen, dass das gewählte Modell keine Konkurrenz zu den etablierten Frameworks darstellt, sondern eine notwendige, kontextspezifische Adaption ist. Es übersetzt die Prinzipien der Reifegradmessung in ein Format, das für die detaillierte technische Planung und Bewertung im Rahmen des BSI-Grundschutzes und der OSCAL-Automatisierung den größtmöglichen, direkten Nutzen stiftet.

---

## Einrichtung in der Google Cloud Platform (GCP)

Bevor der Job ausgeführt werden kann, müssen einige einmalige Einrichtungsschritte in Ihrem Google Cloud-Projekt durchgeführt werden.

### Benötigte Dienste (APIs)

Stellen Sie sicher, dass die folgenden Dienste in Ihrem GCP-Projekt aktiviert sind. Wenn nicht, können Sie sie über die Suchleiste in der GCP Console finden und aktivieren.

1.  **Vertex AI API:** Notwendig, um auf das Gemini-KI-Modell zuzugreifen.
2.  **Cloud Storage API:** Notwendig, um auf die PDF-Dateien und die Ergebnisdatei zuzugreifen.
3.  **Cloud Run Admin API:** Notwendig, um den Cloud Run Job zu erstellen und zu verwalten.
4.  **Cloud Build API:** Notwendig, um das Skript in ein lauffähiges Container-Image zu verpacken.

### Cloud Storage einrichten

Sie benötigen einen "Bucket" in Google Cloud Storage. Ein Bucket ist wie ein übergeordneter Ordner für Ihre Dateien in der Cloud.

1.  **Erstellen Sie einen Bucket:** Falls noch nicht vorhanden, erstellen Sie einen neuen Bucket (z.B. mit dem Namen `bsi-oscal-data`).
2.  **Erstellen Sie die Ordnerstruktur:** Innerhalb dieses Buckets benötigen Sie zwei Ordner:
    *   `BSI_GS2023/`: In diesen Ordner laden Sie alle BSI-PDF-Dateien hoch, die verarbeitet werden sollen.
    *   `results/`: Dieser Ordner ist anfangs leer. Das Skript wird die finale, zusammengefügte JSON-Datei hier ablegen.

## Ausführung des Jobs

Der Prozess wird als "Cloud Run Job" ausgeführt. Dies geschieht in zwei Schritten: Zuerst wird der Job einmalig "deployed" (installiert), und danach kann er beliebig oft "executed" (ausgeführt) werden.

### Schritt 1: Einmaliges Deployment des Jobs

Dieser Befehl muss nur einmal ausgeführt werden (oder immer dann, wenn Sie Änderungen am Code oder an den Anweisungen vornehmen). Er liest alle Projektdateien, verpackt sie in einen sogenannten "Container" und macht diesen als Job in der Cloud verfügbar.

Öffnen Sie die **Cloud Shell** in Ihrem GCP-Projekt (das ist eine Kommandozeile direkt im Browser).

Führen Sie den folgenden Befehl aus. **Ersetzen Sie dabei die Platzhalter!**

```bash
gcloud run jobs deploy bsi-oscal-converter \
    --source . \
    --tasks 1 \
    --set-env-vars="GCP_PROJECT_ID=IHR_PROJEKT_ID,BUCKET_NAME=IHR_BUCKET_NAME" \
    --max-retries 1 \
    --region us-central1
```

**Erklärung der Platzhalter und Optionen:**
*   `bsi-oscal-converter`: Dies ist der Name, den Sie Ihrem Job geben. Sie können ihn ändern.
*   `--source .`: Sagt dem Befehl, dass er alle Dateien im aktuellen Verzeichnis verwenden soll.
*   `GCP_PROJECT_ID=IHR_PROJEKT_ID`: Ersetzen Sie `IHR_PROJEKT_ID` mit der ID Ihres GCP-Projekts.
*   `BUCKET_NAME=IHR_BUCKET_NAME`: Ersetzen Sie `IHR_BUCKET_NAME` mit dem Namen des Storage Buckets, den Sie zuvor erstellt haben.
*   `--region us-central1`: Die Region, in der der Job ausgeführt wird. Diese können Sie bei Bedarf ändern.

### Schritt 2: Ausführen des Jobs

Nachdem der Job deployed wurde, können Sie ihn jederzeit starten, um die PDF-Dateien zu verarbeiten.

Führen Sie dazu einfach diesen Befehl in der Cloud Shell aus:

```bash
gcloud run jobs execute bsi-oscal-converter --region us-central1
```

Der Job startet nun. Sie können den Fortschritt in der Google Cloud Console unter **Cloud Run > Jobs** verfolgen. Dort finden Sie Ihren Job (`bsi-oscal-converter`) und können auf die einzelnen Ausführungen ("Executions") klicken, um die **Logs** einzusehen. Die Logs zeigen Ihnen in Echtzeit an, welche Datei gerade verarbeitet wird, ob Fehler auftreten und wann der Job beendet ist.

### Optional: Test-Modus

Das Skript hat einen eingebauten Test-Modus. Wenn dieser aktiviert ist, werden **nur die ersten 10 Dateien** verarbeitet. Das ist nützlich, um schnell zu testen, ob alles funktioniert, ohne den gesamten (und potenziell teuren) Prozess durchlaufen zu müssen.

Um den Job im Test-Modus auszuführen, können Sie die Konfiguration temporär überschreiben:

```bash
# Führt den Job aus und setzt die 'test'-Variable auf 'true'
gcloud run jobs execute bsi-oscal-converter \
    --region us-central1 \
    --update-env-vars="test=true"
```

Nach Abschluss des Laufs finden Sie die zusammengeführte JSON-Datei im `results/`-Ordner Ihres Cloud Storage Buckets.
