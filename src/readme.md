# BSI-Grundschutz zu OSCAL: Die automatisierte Konvertierungspipeline

Dieses Projekt stellt eine leistungsstarke, automatisierte Pipeline zur Verfügung, um BSI-Grundschutz-„Baustein“-PDF-Dokumente in ein reichhaltiges, strukturiertes und OSCAL-konformes JSON-Format zu konvertieren. Es nutzt die fortschrittlichen Fähigkeiten des `gemini-2.5-pro`-Modells von Google, um den Inhalt nicht nur zu übersetzen, sondern ihn auch mit einem mehrstufigen Reifegradmodell und kontextbezogenen Informationen anzureichern. Dadurch wird der finale Katalog sofort für Analysen und das Compliance-Management nutzbar.

Das System ist als serverloser **Google Cloud Run Job** konzipiert und arbeitet **inkrementell**. Es liest intelligent einen bestehenden Master-OSCAL-Katalog, verarbeitet neue oder aktualisierte PDFs und führt die Ergebnisse nahtlos zusammen, indem es neue „Bausteine“ hinzufügt oder bestehende überschreibt.

### Hauptmerkmale

*   **Vollautomatische Konvertierung:** Wandelt rohe PDF-Inhalte ohne manuellen Eingriff in strukturiertes OSCAL-JSON um.
*   **Inkrementelle Updates:** Fügt intelligent neue Bausteine hinzu oder überschreibt bestehende in einer Master-Katalogdatei, was den Prozess wiederholbar und effizient macht.
*   **Kontextbezogene Anreicherung:** Extrahiert einleitende Kapitel (Einleitung, Zielsetzung, Modellierung) und die vollständige Gefährdungslage in strukturierte `parts`, um wichtigen Kontext direkt im Katalog bereitzustellen.
*   **G++-konforme Praktiken:** Jede Anforderung wird in eine der definierten Praktiken einsortiert.
*   **OSCAL-konforme Anforderungs-Klassen:** Jede Anforderung wird einer Klasse gemäß der offiziellen OSCAL-Spezifikation zugewiesen.
*   **BSI-Level:** Jede Anforderung erhält ein Level basierend auf den BSI-Grundschutz-Kategorien Basis, Standard und Erhöht in den neuen G++-konformen Stufen 1 bis 5.
*   **5-stufiges Reifegradmodell:** Erzeugt fünf verschiedene Reifegradstufen für jede einzelne Anforderung und ermöglicht so eine granulare Bewertung, die über einfache Compliance hinausgeht.
*   **ISMS-Phasen-Zuordnung:** Ordnet jede Anforderung einer Phase des ISMS-Lebenszyklus (z. B. Umsetzung, Betrieb) zu, um eine bessere Prozessintegration zu ermöglichen.
*   **CIA-Schutzziel-Analyse:** Bestimmt, ob eine Anforderung die Vertraulichkeit, Integrität oder Verfügbarkeit beeinflusst.

---

# Bereitgestellte Werkzeuge

## Automatisierte OSCAL-Komponentengenerierung aus dem BSI-Katalog

Das `g2oscal`-Tool ist als **einfache Möglichkeit konzipiert, BSI-Grundschutz-Bausteine in einen deutschen OSCAL-Katalog zu konvertieren**. Es verwendet die originalen deutschen PDFs und erzeugt eine qualitativ hochwertige, angereicherte deutsche JSON-Datei.

---

## Der Übersetzungs-Workflow: Erstellung mehrsprachiger Kataloge

Um übersetzte Versionen (z. B. auf Englisch) zu erstellen, kann `translate_oscal` in jede Sprache übersetzen, die die GenAI anbietet.

1.  Führen Sie zuerst das `g2oscal`-Projekt aus, um eine deutsche OSCAL-Datei `BSI_Catalog_....json` zu generieren.
2.  Navigieren Sie zum Geschwisterverzeichnis dieses Projekts: `../translate_oscal`.
3.  Die Skripte in diesem Verzeichnis sind speziell dafür konzipiert, die deutsche OSCAL-JSON-Datei als **Eingabe** zu verwenden und deren Inhalt mithilfe eines KI-Modells in andere Sprachen zu übersetzen, wobei die gesamte OSCAL-Struktur sorgfältig beibehalten wird.

Diese Trennung der Aufgaben (Separation of Concerns) stellt sicher, dass die Kerndatenerzeugung robust ist und die Übersetzung als unabhängiger, nachfolgender Schritt verwaltet werden kann.

---

## Erstellen von Komponentendefinitionen

Das Projekt `oscal_components_from_grundschutz` enthält ein Skript, das darauf ausgelegt ist, automatisch angereicherte OSCAL-Komponentendefinitionen aus einem BSI-IT-Grundschutz-Katalog zu generieren. Das Skript identifiziert einzelne „Bausteine“ aus dem Quellkatalog, erstellt für jeden eine Basis-Komponentendefinition und verwendet anschließend das Google Vertex AI Gemini Pro-Modell, um intelligent relevante Anforderungen aus anderen Bausteinen zu finden und hinzuzufügen. Um die eher statische Komponente für die „Prozess-Module“ / „Prozessbausteine“ zu generieren, existiert ebenfalls ein kleineres Skript: `create_prozessbausteine_component.py`. Dieses wird einmalig ausgeführt.

Die endgültige Ausgabe ist ein Satz OSCAL-konformer JSON-Dateien, eine für jeden technischen Baustein, die in einem Google Cloud Storage (GCS) Bucket gespeichert werden.

---

## Qualitätssicherung

Das Werkzeug `quality_control` nimmt OSCAL-Komponentendefinitionen und einen Katalog entgegen und führt einen anspruchsvollen, vielschichtigen Zyklus zur Qualitätskontrolle und Anreicherung eines OSCAL-basierten Sicherheitskatalogs durch. Es geht über einfache Linting- oder Syntaxprüfungen hinaus, indem es ein großes Sprachmodell (Google Gemini 2.5 Pro) verwendet, um die semantische Bedeutung, den Kontext und die Vollständigkeit von Sicherheitsanforderungen zu analysieren.

Es fügt dem Katalog Kommentare in einem Teil namens „prose_qs“ hinzu und ergänzt neue Anforderungen, wenn der aktuelle Satz nicht vollständig ist.

---

# Angereicherte Datenmodelle

## 1. Kontextbezogene Informationen (`parts`)

Um den Nutzen des Katalogs zu erhöhen, extrahiert die Pipeline nun wichtige einleitende und kontextbezogene Kapitel aus jedem Baustein-PDF. Diese Informationen werden im `parts`-Array jeder `bausteinGroup` gespeichert, sodass Benutzer den Zweck und die damit verbundenen Risiken verstehen können, ohne auf das Original-PDF zurückgreifen zu müssen.

*   **1. Einleitung:** Ein ausklappbarer Abschnitt, der den Prosa-Text aus den Kapiteln 1.1, 1.2 und 1.3 enthält.
*   **2. Gefährdungslage:** Ein ausklappbarer Abschnitt, der jede relevante Gefährdung auflistet, wobei jede Gefährdung mit ihrem offiziellen Titel und ihrer vollständigen Beschreibung dargestellt wird.

## 2. Das 5-stufige Reifegradmodell

Ein Kernziel dieses Projekts ist es, die OSCAL-Daten mit einer qualitativen Bewertungsebene anzureichern. Zu diesem Zweck wird jede aus dem BSI-Grundschutz extrahierte Anforderung einem 5-stufigen Reifegradmodell zugeordnet. Dieses Modell ermöglicht eine granulare und differenzierte Bewertung der Umsetzungsqualität von Sicherheitsmaßnahmen, die weit über eine rein binäre (erfüllt/nicht erfüllt) Konformitätsaussage hinausgeht.

*   **Stufe 1: Partial (Teilweise umgesetzt)**
*   **Stufe 2: Foundational (Grundlegend umgesetzt)**
*   **Stufe 3: Defined (Definiert umgesetzt)** - **Baseline**
*   **Stufe 4: Enhanced (Erweitert umgesetzt)**
*   **Stufe 5: Comprehensive (Umfassend umgesetzt)**

**Strategischer Wert des Modells:**
Das Modell dient als strategisches Instrument für Informationssicherheits-Managementsysteme (ISMS). Es ermöglicht Organisationen, ihre aktuelle Sicherheitsposition präzise zu bewerten (Ist-Analyse) und unterstützt die Definition von zielgerichteten, risikobasierten Soll-Zuständen (Soll-Architektur). Durch die Quantifizierung der Umsetzungsqualität können Ressourcen effizienter zugewiesen und Verbesserungsbereiche im Sinne eines kontinuierlichen Verbesserungsprozesses (KVP) systematisch identifiziert und priorisiert werden.

Das KI-Modell wurde trainiert, um für jede Anforderung fünf qualitative Varianten zu generieren. Der normative Text aus dem BSI-Kompendium für die jeweilige Anforderung dient als Referenz für die Reifegradstufe 3 („Defined“). Die anderen Stufen werden durch logische Extrapolation abgeleitet, um ein konsistentes und nachvollziehbares Bewertungsgerüst zu schaffen.

### Stufe 1: Teilweise (Partial)
*   **Beschreibung:** Die Anforderung wird nur sporadisch, auf Ad-hoc-Basis oder in einem sehr begrenzten Teil ihres vorgesehenen Geltungsbereichs umgesetzt. Die Umsetzung ist inkonsistent, weist erhebliche Abdeckungslücken auf und adressiert nur einen Bruchteil des beabsichtigten Risikos. Es handelt sich oft um eine reaktive, isolierte Maßnahme statt um einen Teil einer geplanten Strategie.
*   **Schlüsselmerkmale:** Ad-hoc-Reaktionen, inkonsistente Anwendung, hoher manueller Aufwand für Punktlösungen, hohes verbleibendes Restrisiko.

---

### Stufe 2: Grundlegend (Foundational)
*   **Beschreibung:** Die Anforderung ist über ihren gesamten vorgesehenen Geltungsbereich umgesetzt, stützt sich jedoch hauptsächlich auf Standardkonfigurationen (Out-of-the-Box) ohne tiefgreifende Anpassung an spezifische organisatorische Richtlinien oder Risiken. Obwohl eine grundlegende Abdeckung besteht, wird ihre Wirksamkeit oft nur durch manuelle Überprüfung sichergestellt und ist noch nicht optimiert.
*   **Schlüsselmerkmale:** Vollständige Baseline-Abdeckung, Verwendung von Standardeinstellungen, fehlende Anpassung und Härtung, konsistent, aber nicht maßgeschneidert.

---

### Stufe 3: Definiert (Defined)
*   **Beschreibung:** Die Umsetzung der Anforderung folgt einem dokumentierten, standardisierten und wiederholbaren Prozess. Die Konfigurationen sind bewusst auf die unternehmensspezifischen Sicherheitsrichtlinien und Risikoanalysen zugeschnitten. Obwohl der Prozess zuverlässig ist, kann er noch weitgehend manuell sein und ist noch nicht tief in andere Sicherheitssysteme integriert. **Diese Stufe stellt die Baseline für eine ordnungsgemäß und nachweisbar betriebene Sicherheitsmaßnahme dar.**
*   **Schlüsselmerkmale:** Dokumentierter und wiederholbarer Prozess, Konfigurationen sind an Unternehmensrichtlinien angepasst, Überprüfbarkeit der Umsetzung, Erfüllung der Kernanforderung („MUSS“-Anforderung).

---

### Stufe 4: Erweitert (Enhanced)
*   **Beschreibung:** Aufbauend auf dem definierten Prozess werden zusätzliche Kontrollen und Optimierungen implementiert, die über die Basisanforderung hinausgehen. Dies umfasst typischerweise die Umsetzung wichtiger „SOLLTE“-Empfehlungen des BSI, die Verwendung gehärteter Konfigurationen, die Einführung von Automatisierungs- und Überwachungstechniken zur Steigerung der Effektivität sowie die formale Integration mit angrenzenden Prozessen. Die Umsetzung ist nachweislich widerstandsfähiger als die Baseline.
*   **Schlüsselmerkmale:** Umsetzung von „SOLLTE“-Empfehlungen, erhöhte Wirksamkeit und Widerstandsfähigkeit, erste Automatisierung und proaktive Überwachung, formalisierte Prozesse.

---

### Stufe 5: Umfassend (Comprehensive)
*   **Beschreibung:** Die Anforderung ist als Best-Practice-Lösung implementiert und tief in die Sicherheitsarchitektur (Defense-in-Depth) integriert. Sie ist hochwirksam, oft weitgehend automatisiert und wird proaktiv überwacht und kontinuierlich optimiert. Diese Stufe spiegelt eine reife, vorausschauende Sicherheitsstrategie wider, die oft alle relevanten „SOLLTE“-Empfehlungen sinnvoll kombiniert und verfeinert.
*   **Schlüsselmerkmale:** Best-Practice-Implementierung, hochgradig automatisiert und integriert, kontinuierliche Überwachung und Optimierung, proaktives Sicherheitsniveau.

---

## 3. ISMS-Phasen-Zuordnung

Um den strategischen Wert des Katalogs zu erhöhen und die Lücke zwischen technischen Anforderungen und Managementprozessen zu schließen, wird jede Sicherheitsanforderung einer spezifischen Phase des Lebenszyklus eines Informationssicherheits-Managementsystems (ISMS) zugeordnet. Diese Klassifizierung ist von etablierten Frameworks wie ISO/IEC 27001 und dem Plan-Do-Check-Act (PDCA)-Zyklus inspiriert und bietet einen prozessorientierten Kontext für jede Anforderung.

**Strategischer Wert der Phasen-Zuordnung:**
Diese Zuordnung ermöglicht es Stakeholdern – wie CISOs, Sicherheitsbeauftragten und Projektmanagern – Anforderungen basierend auf ihrem aktuellen strategischen oder operativen Fokus zu filtern und zu priorisieren. Sie hilft, technische Sicherheitsmaßnahmen direkt in die umfassenderen Aktivitäten des Risikomanagements, der Projektplanung und der kontinuierlichen Verbesserung zu integrieren, wodurch die Governance und die prozessuale Verankerung der Informationssicherheit gestärkt werden.

Das KI-Modell ist darauf trainiert, jeder Anforderung die logisch am besten passende Phase zuzuordnen, wobei „Umsetzung“ für die meisten technischen Anforderungen als Standard dient.

### Die ISMS-Phasen im Detail

---
#### **Initiierung (Initiation)**
*   **Beschreibung:** Diese Phase umfasst die strategische Vorbereitung und Zieldefinition für sicherheitsrelevante Initiativen. Sie beinhaltet den Aufbau von Governance-Strukturen, die Festlegung des ISMS-Geltungsbereichs und die Formulierung der zentralen Informationssicherheitsleitlinie. Anforderungen in dieser Phase sind typischerweise grundlegend und richtlinienbasiert.

---
#### **Risikobewertung (Risk Assessment)**
*   **Beschreibung:** Dies beinhaltet die systematische Identifizierung, Analyse und Bewertung von Informationssicherheitsrisiken. Diese Phase ist fundamental, um den notwendigen Schutzbedarf zu ermitteln und angemessene Sicherheitsmaßnahmen abzuleiten. Anforderungen im Zusammenhang mit der Identifizierung von Assets und der Bedrohungsanalyse gehören hierher.

---
#### **Risikobehandlung (Risk Treatment)**
*   **Beschreibung:** Dies ist der Prozess der Auswahl und Gestaltung von Maßnahmen, um die in der Bewertungsphase identifizierten Risiken zu adressieren. Er umfasst strategische Entscheidungen darüber, ob ein gegebenes Risiko gemindert, vermieden, transferiert oder akzeptiert wird. Anforderungen in dieser Phase sind oft konzeptionell und planungsbezogen.

---
#### **Umsetzung (Implementation)**
*   **Beschreibung:** Diese Phase betrifft die technische und organisatorische Einführung der im Risikobehandlungsplan definierten Sicherheitsanforderungen. Es ist die „Build“-Phase, die konzeptionelle Anforderungen in einen betriebsbereiten Zustand überführt. Der Großteil der technischen BSI-Grundschutz-Anforderungen fällt in diese Kategorie.

---
#### **Betrieb (Operation)**
*   **Beschreibung:** Diese Phase deckt die laufende Ausführung und Wartung der implementierten Sicherheitsanforderungen ab. Sie umfasst Routineprozesse wie Überwachung, Patch-Management, Incident-Handling und die Durchführung regelmäßiger Sicherheitsaufgaben.

---
#### **Audit (Audit)**
*   **Beschreibung:** Dies beinhaltet die periodische und systematische Überprüfung der Wirksamkeit, Effizienz und Konformität des ISMS und seiner Anforderungen. Audits liefern die notwendigen Daten, um die Sicherheitsleistung zu bewerten und zu verifizieren, dass die Anforderungen wie beabsichtigt funktionieren.

---
#### **Verbesserung (Improvement)**
*   **Beschreibung:** Diese Phase konzentriert sich auf die kontinuierliche Optimierung des ISMS auf der Grundlage der Ergebnisse aus Audits, Leistungskennzahlen und der Analyse von Sicherheitsvorfällen. Sie schließt den PDCA-Zyklus und treibt die fortlaufende Entwicklung und Reifung der Sicherheitsposition der Organisation voran.
