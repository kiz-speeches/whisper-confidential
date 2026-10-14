# Whisper mit CPU-Attestation und normaler GPU

Eigenständiges Repository für Code, Browser-Prüfer, feste Build-Eingaben und Policy-Referenzen. Einstieg in den lokalen Nachbau, Release-Manifest und lokal gestarteten Browser-Client: [release/README.md](release/README.md). Versionsangaben sind bisher nicht an eine durchgesetzte Workload-Policy gebunden; die folgenden Infrastruktur- und Testangaben dokumentieren den aktuellen Prototyp.

Laufender Prototyp unter **https://whisper.speeches.dev**: Browser → verschlüsselter Anwendungskanal → kleiner CPU-Gateway in AMD SEV-SNP/CoCo → normales GPU-Whisper → verschlüsseltes Transkript zurück zum Browser.

Der CPU-Gateway läuft auf `sec2` als Deployment `whisper-cpu-gateway` mit `kata-qemu-snp`. Whisper small/CUDA läuft weiterhin auf einer RTX PRO 4500 auf `sec1` als `whisper-gpu-prototype`. Beide stehen im Namespace `confidential-inference`. Die GPUs auf sec2 bleiben im normalen Betrieb; die Reportänderung benötigt kein GPU-CC.

## Ausprobieren

1. https://whisper.speeches.dev öffnen. Der Browser fordert einen frischen echten AMD-Report an und prüft ihn lokal.
2. „Attestation-Report ansehen“ öffnen. Die Prüfergebnisse sind sichtbar; der vollständige Report mit Zertifikaten ist herunterladbar.
3. Die CPU-Prüfung und anschließende GPU-Verarbeitung ohne CC bestätigen.
4. Sprache wählen, Aufnahme starten oder Datei öffnen. Anschließend Text bearbeiten, kopieren oder herunterladen.

Bei ungültigem Nachweis bleiben Aufnahme, Upload und Bestätigung gesperrt. Nach einem Übertragungsfehler bleiben ausstehende Live-Abschnitte im Browser: neuen CPU-Nachweis anfordern und erneut bestätigen. Eine Sitzung läuft nach 30 Minuten ab.

## Was wirklich geprüft wird

Die Hardware liefert einen SEV-SNP-v5-Report direkt aus dem CPU-Gast des Gateways. Der Browser verwendet seinen eigenen zufälligen 32-Byte-Nonce und ein frisches ECDH-P-256-Schlüsselpaar. Der Gateway erzeugt ebenfalls ein frisches Schlüsselpaar innerhalb seines Gasts.

`REPORT_DATA` enthält die 64 ASCII-Hexzeichen von:

```text
SHA256("whisper-cpu-tee-v1\0" || browser_nonce || gateway_public_key || browser_public_key || session_id_bytes)
```

Die 64-Byte-ASCII-Kodierung ist erforderlich, weil der CoCo-Agent `runtime_data` als Literal übernimmt. Der Browser berechnet den Wert selbst. Ein vom Server behauptetes `verified: true` wird nicht verwendet.

Der lokale Go/WASM-Prüfer prüft:

- AMD-ARK als eingebetteten festen Vertrauensanker, ASK/VCEK-Zertifikatskette und Gültigkeitszeiten.
- Signierte AMD-Sperrliste, deren Gültigkeit und eine eventuelle Sperrung des ASK.
- ECDSA-P-384/SHA-384-Signatur des ursprünglichen binären Reports.
- Nonce-/Schlüsselbindung, VMPL 0, VCEK-Signer und Gast-Policy `0x30000`: Debug und Migration aus.
- Administratorseitig erfasste CPU-Gast-Startmessung; keine automatische Übernahme eines beliebigen Server-Messwerts.
- Turin-CPU-Format, Hardware-ID und Firmware-TCB einschließlich FMC; Mindeststände FMC 1, Bootloader 3, TEE 2, SNP 6, Microcode 98 sowie aktuelle, beim Start und festgeschrieben verwendete TCB-Stände.

Der Prüfer unterstützt bewusst die tatsächlich vorhandene Kombination Turin/Report v5. Andere CPUs oder Report-Layouts werden abgewiesen. Der ARK stammt aus `google/go-sev-guest v0.15.0`, Datei `verify/trust/ask_ark_turin_vcek.pem`; die lokale Kopie stimmt mit der offiziellen AMD-KDS-CA-Datei überein. Die Prüfung verwendet Go-Standardbibliotheken. Die bisherige Bibliothek wird nicht als generischer Turin-Prüfer verwendet, weil ihre TCB- und Zertifikatparser das hier benötigte FMC-Layout noch nicht vollständig abdecken.

Protokollspezifikationen: [AMD SNP ABI](https://www.amd.com/en/developer/sev.html), [AMD VCEK/KDS 57230 Rev. 1.00](https://docs.amd.com/api/khub/documents/dWGhwYpo1Wv51rJN4d~47g/content), [CoCo-Attestation-Agent](https://confidentialcontainers.org/docs/features/get-attestation/).

## Verschlüsselung und Vertrauensgrenzen

Der GPU-Teil des Prototyp-Reports ist ein ausdrücklich leerer Platzhalter: `gpu_attestation.evidence: null`, `status: "not_available"`, `placeholder: true`, `verified: false`, `confidential_computing: false`. Er steht neben dem unveränderten signierten AMD-Report und erscheint auch im Download. Der Browser erzeugt diesen Status selbst und übernimmt keine behauptete erfolgreiche GPU-Prüfung vom Server. `verified` aus dem CPU-Prüfer gilt ausschließlich für `verification_scope: "cpu_guest_and_session_key"`; `full_attestation_verified` bleibt false. Fehlende oder ungültige CPU-Evidence führt weiterhin zum Abbruch, niemals zu einer simulierten CPU-Quote.

Browser und CPU-Gateway leiten aus ECDH mit HKDF-SHA256 zwei getrennte AES-256-GCM-Schlüssel für Anfrage und Antwort ab. Salt ist die Browser-Challenge. Zufällige 96-Bit-IVs und authentifizierte Daten binden Sitzung, laufende Sequenz, Richtung und Sprache. Wiederholte Sequenzen werden abgewiesen. Schlüssel werden nur im Arbeitsspeicher gehalten. Der Browser überträgt verschlüsselte Audio-Bytes und entschlüsselt das zurückkommende Transkript lokal.

**Für die GPU gibt der CPU-Gateway das Audio als Klartext über einen normalen internen HTTP-Aufruf weiter. Die GPU und dieser interne Abschnitt sind nicht vertraulich geschützt.** Das gesamte Verfahren ist deshalb noch nicht gegen Kubernetes-/Host-Betreiber abgesichert.

Die CPU-Gast-Messung weist außerdem noch nicht die Anwendung nach: `HOST_DATA` ist null, eine restriktive, gemessene Agent-/Container-Policy fehlt. Die vorhandene Policy erlaubt weiterhin Verwaltungszugriffe. Eine Schlüsselbindung im Hardware-Report beweist ohne verifizierte Anwendungspolicy allein nicht, dass ein bösartiger Betreiber den privaten Schlüssel ausschließlich im gewünschten Programm hält. Die Oberfläche weist deshalb `workload_policy_verified: false` und `gpu_confidential_computing: false` aus.

Auch die Webseite selbst ist eine Vertrauensvoraussetzung: Wird ihr JavaScript vom Betreiber ersetzt, kann es die lokale Prüfung manipulieren. Für Schutz vor einem aktiv bösartigen Betreiber braucht es später einen unabhängig bezogenen/pinnierten Client, geprüfte Workload-Policy, unveränderliches Anwendungsimage und GPU-CC mit eigenem Nachweis. `/v1/runtime` ist lediglich eine Betriebsinformation; die eigentliche Verifikation findet im Browser statt.

Der AMD-VCEK-Abruf übermittelt Chip-ID und TCB-Werte an `kdsintf.amd.com`. Der Nutzer hat diese Weitergabe am 2026-10-11 ausdrücklich freigegeben. Zertifikate und CRL werden eine Stunde im Gateway gecacht; eine abgelaufene/ungültige CRL wird im Browser abgewiesen. Der Abruf ist über `AMD_KDS_ENABLED=true` freigeschaltet.

## Geprüfter Stand am 2026-10-14

Die neue Reportstruktur ist öffentlich ausgerollt und im Browser mit echter CPU-Evidence geprüft. Anzeige und Download enthalten den leeren GPU-Platzhalter; auch eine manipulierte Serverantwort mit behaupteter GPU-Verifikation bleibt im Browser nicht verifiziert. Bestätigung vor Audio, echte GPU-Transkription über den verschlüsselten Anwendungskanal, Report-Download, Ablehnung falscher Challenge/Signatur und wiederverwendeter Quotes sowie Mobilansicht bestanden erneut. Die bisherigen AMD-Vertrauensanker und der unabhängig erfasste Referenzmesswert wurden nicht verändert.

Der CPU-Gateway war nach der Hostwartung auf null Instanzen skaliert; die öffentliche Seite lieferte 503. Beim Wiederanlauf auf dem Coconut-Hostkernel `7.2.2-0_coconutsvsm_20260928.fc44.x86_64` scheiterte QEMUs Datenträger-Hotplug mit `aio=io_uring ... not available`. Die CPU-SNP-Konfiguration verwendet deshalb nun `block_device_aio = "threads"`; nur dieser Wert wurde mit vorheriger Sicherung geändert. Das Installationsrezept enthält den gleichen Wert. Keine Lockerung von SELinux/Seccomp, kein GPU-Moduswechsel und kein Host-Reboot. Der neue Gateway ist Ready und die echte CPU-Prüfung besteht mit unveränderter Referenzpolicy. Das bedeutet weiterhin keine verifizierte Anwendungspolicy oder GPU-CC.

Aktuelle Nachweise: `evidence/gpu-placeholder-2026-10-14/cpu-attestation-browser.json`, `cpu-attestation-report.json`, Desktop-/Mobilbilder und Deployment-Snapshots. `test-gpu-placeholder.cjs` und vier lokale Gateway-Protokolltests verwenden ausdrücklich simulierte CPU-Evidence für Vertragstests und zählen nicht als Hardware-Nachweis.

## Geprüfter Stand am 2026-10-11

Die Tests verwenden ausschließlich öffentliches JFK-Testaudio oder synthetische deutsche Sprache und ein simuliertes Browser-Mikrofon. Das echte Nutzer-Mikrofon wurde nicht aktiviert.

- Echter CPU-Gateway-Report mit AMD-Signatur, Zertifikaten, Sperrliste und lokalem WASM-Prüfer erfolgreich geprüft.
- Öffentliche HTTPS-Adresse: Bestätigung erforderlich, verschlüsselter Datei-Upload und verschlüsselte Antwort, tatsächliche CUDA-Inferenz und vollständiger Report-Download.
- Veränderte Signatur, falsche Challenge und Wiederverwendung einer älteren Quote sperren die Oberfläche; kein Audio wird gesendet.
- Native Negativtests für Report-Signatur, Messwert, Policy, TCB, reservierte Bits, Zertifikats- und CRL-Signaturen sowie fehlende Zertifikate.
- Vollständige Live-Aufnahme einschließlich letztem unvollständigem Abschnitt, Netzfehler mit erhaltenem Audio und Wiederholung nach neuer Prüfung, deutsches Audio, Textbearbeitung/Kopieren/Download, ungültiges Audio und simulierte Mikrofon-Ablehnung.
- Desktop/Mobilansicht ohne horizontalen Überlauf und ohne Browser-Skriptfehler.
- Lokale Protokolltests mit ausdrücklich simuliertem Report/GPU: ECDH-Bindung, beide Verschlüsselungsrichtungen, Manipulationsschutz, Sequenz-Replay und abgelaufene Sitzungen. Diese Tests gelten nicht als Hardware-Nachweis.

Nachweise: `evidence/cpu-attestation-browser.json`, `evidence/cpu-tee-public-flow.json`, `evidence/cpu-attestation-negative-checks.json`, `evidence/cpu-gateway-raw-report.json`. Die früheren `public-flow.json`/`public-https.json` dokumentieren die vorausgehende Stufe ohne CPU-Attestation.

## Deployment und Build

Das Entwicklungsdeployment verwendet ein festes Python-Basisimage, einen Init-Container und unveränderliche Source-/WASM-ConfigMaps. Der Browser-Prüfer wird in mehreren ConfigMaps transportiert und im Gast mit SHA-256 geprüft. So ist für den aktuellen Prototyp kein Harbor-Admin-Passwort erforderlich. Der vorhandene Registry-Robot hatte keine Push-Berechtigung; die automatische Freigabeprüfung hat die Nutzung des Admin-Passworts abgelehnt. Das CPU-Image wurde lokal gebaut, aber nicht in Harbor veröffentlicht. Für die künftige Pipeline liegt `attestation/Dockerfile` vor.

Die Quellen sind außerhalb des Flux-Reconcile-Pfads; kein Git-Push/Pipeline-Release wurde vorgenommen. `static/attestation-policy.json` enthält den separat erfassten CPU-Gast-Messwert. Ein neues Gastimage oder andere Startparameter erfordern einen bewusst aktualisierten Referenzwert; der Browser verweigert abweichende Werte.

```bash
export KUBECONFIG=/home/yannes/Documents/speeches-banchmark/.tmp/kubeconfig-sec
bash prototype/attestation/build.sh
python prototype/attestation/deploy.py
kubectl -n confidential-inference rollout status deployment/whisper-cpu-gateway
kubectl apply -f prototype/k8s/ingress.yaml
```

`deploy.sh` richtet auch den normalen GPU-Backend ein. GPU-Codeänderungen benötigen dessen Neustart. Für reine CPU-/UI-Änderungen genügt der Ablauf oben; der GPU-Backend bleibt laufen. `k8s/gpu-only-ingress.yaml` ist eine frühere Routing-Konfiguration für Diagnose; sie deaktiviert den CPU-Gateway im öffentlichen Datenpfad und sollte nicht versehentlich angewendet werden.

Der CPU-Dienst fordert 500m CPU/512 MiB an, maximal 2 CPU/2 GiB plus RuntimeClass-Overhead. Seine Aufgabe ist Report-/Sitzungsverwaltung und Ver-/Entschlüsselung; Whisper und Modellgewichte bleiben außerhalb. Aktuell werden Python-Abhängigkeiten noch im CPU-Gast installiert. Ein späteres Pipeline-Image kann diesen Startaufwand beseitigen:

```bash
docker build -f prototype/attestation/Dockerfile -t whisper-cpu-gateway:dev prototype
```

Für das GPU-Pipeline-Image liegt der getrennte `prototype/Dockerfile` mit eingebautem Modell und gepinnten Dependencies vor; dieses GPU-Image wurde noch nicht gebaut/veröffentlicht. Die GPU verwendet faster-whisper 1.2.1, CTranslate2 4.8.2 und PyAV 16.0.1; neuere PyAV-Versionen sind mit diesem faster-whisper-Aufruf inkompatibel.

## API und Grenzen

- `GET /health`: CPU-Gateway und GPU-Bereitschaft.
- `GET /v1/runtime`: ehrlicher Betriebsstatus, kein kryptographischer Nachweis.
- `POST /v1/attestation`: Nonce und Browser-Public-Key; Report, Zertifikate, CRL und gebundener Gateway-Public-Key zurück.
- `POST /v1/audio/transcriptions`: AES-GCM-verschlüsselte Audio-Bytes mit `X-Session`, `X-IV`, `X-Sequence`, `X-Language`; verschlüsselte JSON-Transkription zurück.

Live-Audio wird in etwa achtsekündigen Mono-WAV-Abschnitten mit 16 kHz verarbeitet. Das ist Abschnitts-Transkription, noch kein inkrementelles Whisper-Decoding; Wörter an Grenzen und längerer Kontext können verloren gehen. Deutsches Testaudio enthält einen Erkennungsfehler. Aufnahme maximal 30 Minuten, Datei maximal 64 MiB, Audio-Anfragen maximal vier gleichzeitig am Ingress, maximal zwei pro Gateway zur GPU. Verlorene/unterbrochene Abschnitte bleiben nur im Browser-Speicher; Neuladen löscht sie.

Der Dienst ist ohne Login öffentlich erreichbar. Audio wird begrenzt auf 120 Anfragen/Minute mit Burst 30 und maximal 65 MiB Gesamtnachricht; Report-Anfragen auf 20/Minute, Burst 8 und 4096 Byte. Maximal 128 CPU-Sitzungen pro Gateway. Traefik darf verschlüsselte Anfragen über 1 MiB temporär puffern. Es gibt keine dauerhafte Audio-/Transkript-Speicherung; der normale GPU-Service kann Uploads vorübergehend im ephemeren Dateisystem ablegen. Meeting-Verwaltung, Sprecherzuordnung, gespeicherte Aufzeichnungen, Accounts und Billing fehlen weiterhin.

Für lokale Diagnose funktioniert Kubernetes-Portforward beim CoCo-Gast nicht; `open.sh` öffnet einen SSH-Tunnel zur internen CPU-Serviceadresse. Für die öffentliche Adresse wird keine lokale Weiterleitung benötigt.
