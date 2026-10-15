# Nachweise prüfen

Dieser Ordner enthält die überprüfbaren Referenzdateien veröffentlichter Builds. Er wird nicht in die Container kopiert. Der [Snapshot für v0.2.0-policy](releases/v0.2.0-policy/README.md) enthält die unveränderten Release-Dateien und eine getrennt gekennzeichnete Zusammenfassung der Hardwaretests vom 14. Oktober 2026.

## Welche Version ist gemeint?

Eine Release-Version wie `v0.2.0-policy` ist ein lesbarer Name. Die verlässlichen Vergleichswerte sind der vollständige Quellcommit, die SHA256-Digests der Images und der erwartete SNP-`HOST_DATA`.

Die Reihenfolge ist: Quellcommit **A** bauen, daraus Images und Nachweise erzeugen, die Nachweise in einem späteren Repository-Commit **B** ablegen. Das Manifest nennt weiterhin **A**. **B** macht die fertigen Dateien im Repository anklickbar; es ist kein neuer Build derselben Images. Links auf Quellcode müssen daher **A**, Links auf diese Dateien den vollständigen Commit **B** verwenden. Bestehende Release-Tags und Referenzdateien dürfen nicht nachträglich auf andere Inhalte umgestellt werden. Änderungen an Anwendung, Modell oder Policy erhalten eine neue Release-Version mit neuen Prüfdaten.

Beim unabhängigen Nachbau zuerst den im Manifest genannten Quellcommit auschecken. `tools/release.py verify` prüft dessen vollständigen Dateibestand; ein Vergleich am späteren Nachweis-Commit würde zurecht andere Quellen melden. Die zwei Pipeline-Builds belegen Wiederholbarkeit auf demselben Runner. Ein eigener Nachbau ist die zusätzliche, unabhängige Prüfung.

## Was von außen geprüft werden kann

| Bestandteil | Nachweis und aktuelle Grenze |
| --- | --- |
| CPU-Gast | Ein frischer, lokal geprüfter AMD-SNP-Bericht muss die erwartete Gastmessung enthalten. Diese Referenz ist administrativ aufgezeichnet; dieses Repository reproduziert den VM-Build nicht aus Quellen. |
| CPU-Anwendung und Abhängigkeiten | Der signierte `HOST_DATA` bindet die exakten InitData-Bytes. Deren Policy erlaubt das freigegebene CPU-Image per Digest mit festem Startvertrag und verbietet Exec sowie Policy-Wechsel. Der Client muss diese Bindung tatsächlich prüfen. |
| Sitzungsschlüssel | Der geprüfte Bericht bindet den Sitzungsschlüssel an die aktuelle Anfrage. Audio und Antwort werden zwischen lokalem Client und CPU-Anwendung verschlüsselt. |
| GPU-Anwendung und Modell | Quellstand, Image und Modell-Dateihashes sind festgelegt. Ihre aktive Ausführung ist derzeit nicht attestiert. Audio verlässt die CPU-TEE im Klartext auf dem Weg zur GPU. |
| Client und Webseite | Der Verifier gehört zu einem getrennten Client-Projekt. Der Nutzer muss dessen Code und Referenzwerte vertrauenswürdig beziehen. Die gehostete Webseite ist selbst kein unabhängiger Vertrauensanker. |

Der Prüfpfad lautet: vertrauenswürdig bezogene Referenz → AMD-Signatur und Gastmessung → signierter `HOST_DATA` → InitData und Policy → erlaubter CPU-Image-Digest → selbst nachvollziehbare Image-Inhalte. Nur Serverangaben zu Versionen oder ein grüner Status aus einer fremden Webseite reichen dafür nicht.

Die Hardwaretests haben unter anderem ein anderes Image, einen anderen Startbefehl, zusätzliche Python-Konfiguration und nachträgliches Exec zurückgewiesen. Ein falscher erwarteter `HOST_DATA` wurde vom Client abgelehnt. Die beigefügte Testzusammenfassung dokumentiert diese Ergebnisse; sie ersetzt keinen frischen signierten Bericht für die eigene Sitzung.

Die Zusage bleibt an Annahmen gebunden: AMD-Hardware und Zertifikatskette, die erwarteten Gast-Komponenten samt Policy-Durchsetzung, Kryptografie sowie der eigene Client und seine Referenzen müssen vertrauenswürdig sein. Sicherheitslücken in diesen Komponenten sind damit nicht ausgeschlossen. Release und Client sind bislang nicht zusätzlich signiert; eine Mindestversion oder ein Rückrufmechanismus ist noch nicht implementiert. Ein Hash allein verhindert außerdem nicht, dass eine alte, weiterhin erlaubte Version angeboten wird.
