---
title: INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx
owner:
  - null
author:
  - null
document_version: 0.1
modified_at: "2026-08-28T12:08:29+00:00"
# Allowed values: work in progress | review version | released
state: null
comment: null
# Allowed values: C0 (frei verwendbar) | C1 (intern) | C2 (vertraulich) | C3 (streng vertraulich)
access_classification:

front_matter_revision: 20260904_1200
---

<!-- Slide number: 1 -->

![images/abstract-corporate-technology-background-in-siemen_2026-06-16T11-04-35_image_DAS_0.jpg](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_001.jpg)

SIEMENS
INTEGRATIONSTEST  ·  TEST-MANAGEMENT
Änderungen an bestehenden
Testfällen
Vorgehensweise und Qualitätskriterien in der Chemnitzer Integrationstestdatenbank
Stand: 16. Juni 2026

### Notes:

<!-- Slide number: 2 -->
ÜBERBLICK
Agenda

01
02
Ausgangslage & Ziel
Vorgehensweise im Überblick
Warum Testfälle geändert werden
Der Änderungsprozess in fünf Schritten

03
04
Worauf zu achten ist
Stolperfallen & Best Practices
Qualitätskriterien für jede Änderung
Typische Fehler vermeiden
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted
2

### Notes:

<!-- Slide number: 3 -->

![images/professional-photograph-of-a-software-integration-_2026-06-16T11-04-41_image_DAS_0.jpg](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_002.jpg)

AUSGANGSLAGE
Warum Testfälle geändert werden
Anforderungen ändern sich

1
Neue oder angepasste Funktionen erfordern eine Aktualisierung bestehender Testfälle.Anhängig davon in Welcher Testumgebung das derzeit aktiv genutzt wird und ob die Testfälle in Moment aktiv in einem laufenden Testprojekt verwendet werden.
Aktive Nutzung  Testfall duplizieren, alten Testfall behalten!

Fehler im Testfall

2
Falsche Erwartungswerte, veraltete Testdaten oder unklare Schritte müssen korrigiert werden. Korrektur in den bestehenden Testfällen!

Systemumgebung wandelt sich

3
Schnittstellen, Versionen und Konfigurationen der Integrationsumgebung entwickeln sich weiter.Anhängig davon in Welcher Testumgebung das derzeit aktiv genutzt wird und ob die Testfälle in Moment aktiv in einem laufenden Testprojekt verwendet werden.
Aktive Nutzung  Testfall duplizieren, alten Testfall behalten!

Qualität & Effizienz

4
Redundante oder instabile Tests werden konsolidiert, um die Aussagekraft zu erhöhen.Korrektur in den bestehenden Testfällen!

SIEMENS
Chemnitzer Integrationstestdatenbank  ·  Unrestricted
3

### Notes:

<!-- Slide number: 4 -->
VORGEHENSWEISE
Der Änderungsprozess bei Fehlern oder Stabilitätsanpassungen

1

2
Bearbeitung
Review & Freigabe
Änderung direkt im Testfall. Bestehende Testergebnisse aus vorhanden Testläufe sind davon unbeeinflusst.
Vier-Augen-Prinzip durch Test-Owner und Fachverantwortliche
Jede Änderung durchläuft den vollständigen Prozess — kein Schritt darf übersprungen werden.
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  Unrestricted
4

### Notes:

<!-- Slide number: 5 -->
VORGEHENSWEISE
Der Änderungsprozess bei Anforderungs- oder Systemumgebungsänderungen

1

2

3

4

5
Kopie des bestehenden Testfalles erzeugen
Umsetzung / Korrektur
Review & Freigabe
Verifikation & Dokumentation
Analyse & Impact
4
Alter Testfall bleibt unberührt, Neuer Testfall wird im Ordner 00_New_Test_Cases erzeugt
Neu erzeugten Testfall versioniert anpassen, Daten und Schritte aktualisieren
Vier-Augen-Prinzip durch Test-Owner und Fachverantwortliche bzw. erweiterten Teilnehmer kreis
Alten Testfall in den Ordner Archiv mit vollständigem Pfad verschieben.
Neuen Testfall von 00_New_Test_Cases zum Zielordner verschieben
Abhängigkeiten, betroffene Produkte bewerten
Jede Änderung durchläuft den vollständigen Prozess — kein Schritt darf übersprungen werden.
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted

### Notes:

<!-- Slide number: 6 -->

1
VORGEHENSWEISE
Kopie des bestehenden Testfalles erzeugen
Der Änderungsprozess bei Anforderungs- oder Systemumgebungsänderungen

Alter Testfall bleibt unberührt, Neuer Testfall wird im Ordner 00_New_Test_Cases erzeugt

![image](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_003.png)

![image](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_004.png)
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted

### Notes:

<!-- Slide number: 7 -->

2
VORGEHENSWEISE
Der Änderungsprozess bei Anforderungs- oder Systemumgebungsänderungen

Umsetzung / Korrektur
Neu erzeugten Testfall versioniert anpassen, Daten und Schritte aktualisieren

![image](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_005.png)
Jede Änderung durchläuft den vollständigen Prozess — kein Schritt darf übersprungen werden.
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted

### Notes:

<!-- Slide number: 8 -->

3
VORGEHENSWEISE
Der Änderungsprozess bei Anforderungs- oder Systemumgebungsänderungen

Review & Freigabe

![image](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_006.png)
Vier-Augen-Prinzip durch Test-Owner und Fachverantwortliche bzw. erweiterten Teilnehmer kreis
Jede Änderung durchläuft den vollständigen Prozess — kein Schritt darf übersprungen werden.
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted

### Notes:

<!-- Slide number: 9 -->

4
VORGEHENSWEISE
Der Änderungsprozess bei Anforderungs- oder Systemumgebungsänderungen

Verifikation & Dokumentation

![image](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_007.png)
Alten Testfall in den Ordner Archiv mit vollständigem Pfad verschieben.
Neuen Testfall von 00_New_Test_Cases zum Zielordner verschieben

![image](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_008.png)
Jede Änderung durchläuft den vollständigen Prozess — kein Schritt darf übersprungen werden.
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted

### Notes:

<!-- Slide number: 10 -->
VORGEHENSWEISE
Der Änderungsprozess bei Anforderungs- oder Systemumgebungsänderungen

5
Analyse & Impact
4
Abhängigkeiten, betroffene Produkte bewerten
Jede Änderung durchläuft den vollständigen Prozess — kein Schritt darf übersprungen werden.
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted

### Notes:

<!-- Slide number: 11 -->
QUALITÄTSKRITERIEN
Worauf bei jeder Änderung zu achten ist
Eindeutige Begründung
Erwartungswerte prüfen

✓

✓
Jede Änderung ist begründet
Soll-Ergebnisse müssen aktuell, präzise und überprüfbar sein.
Keine verdeckte Erweiterung

✓
Testdaten konsistent halten

✓
Scope der Änderung nicht unbemerkt ausweiten.
Keine geteilten Daten zerstören, Wiederverwendbarkeit sichern.
Rückverfolgbarkeit

✓
Verknüpfung zu Anforderung, Version und Verantwortlichem erhalten.
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted
6

### Notes:

<!-- Slide number: 12 -->
LESSONS LEARNED
Stolperfallen & Best Practices
HÄUFIGE STOLPERFALLEN
BEST PRACTICES

Änderung ohne Begründung
Klein und nachvollziehbar ändern
✕
✓
Gemeinsame Testdaten unbemerkt verändert
IAnalyse vor jeder Umsetzung durchführen
✕
✓
Freigabe übersprungen oder nachträglich erteilt
Konsequente Versionierung jeder Testfall-Änderung
✕
✓
Baseline nicht aktualisiert — alte Version bleibt aktiv
Vier-Augen-Prinzip ausnahmslos einhalten
✕
✓
SIEMENS
Chemnitzer Integrationstestdatenbank  ·  restricted
8

### Notes:

<!-- Slide number: 13 -->

![images/abstract-corporate-technology-background-in-siemen_2026-06-16T11-04-35_image_DAS_0.jpg](images/INTEGRATIONSTEST_TESTDATA_MANAGEMENT.pptx_image_009.jpg)

SIEMENS
AUTOREN
Vielen Dank
John Nietsch  ·  Andreas Bohn