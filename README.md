# Whisper Container-API

Dieses Repository macht den Container-Code, seine festen Build-Eingaben und die Prüfungen nachvollziehbar. Es enthält ausschließlich die beiden Container-Dienste und ihre Builds. UI, Browser-Verifier, Accounts, Billing und Kubernetes-Deployment gehören in andere Projekte.

| Ordner | Aufgabe | Code im laufenden Container |
| --- | --- | --- |
| `cpu/` | CPU-Attestation, Sitzungsschlüssel und verschlüsseltes Audio | `api.py`, `evidence.py` |
| `gpu/` | Whisper-Inferenz und Modellprüfung | `api.py`, `verify_model.py` |
| `build/`, `tools/`, `.github/` | Feste Build-Eingaben, Image-Hashes und Pipeline | keiner |
| `tests/` | API-, Kryptografie-, Modell- und Image-Prüfungen | keiner |

Beide Images enthalten daneben ihre Python-Abhängigkeiten; das GPU-Image benötigt außerdem die Whisper-Modellgewichte. `gpu/prepare_model.py` läuft nur beim Build und landet nicht im fertigen Image. Die Docker-Build-Kontexte erlauben ausdrücklich nur die benötigten Dateien.

## APIs

Beide Dienste bieten `GET /health`, `GET /v1/runtime` und `POST /v1/audio/transcriptions`. Die GPU nimmt eine Multipart-Audiodatei und `language` (`de`, `en`, `auto`) entgegen. Die CPU nimmt ausschließlich verschlüsselte Audiodaten einer vorher attestierten Sitzung entgegen. Dafür liefert `POST /v1/attestation` CPU-Evidence und den gebundenen öffentlichen Sitzungsschlüssel. Die kryptografischen API-Tests zeigen den ECDH/HKDF/AES-GCM-Ablauf. Es gibt keine HTML-, Static-, Swagger- oder Browser-Routen.

Die Attestation-Antwort enthält ausschließlich folgenden Nachweis und die daran gebundenen Sitzungsdaten:

```json
{
  "evidence": {"report": "BASE64", "vcek": "BASE64", "ask": "BASE64", "crl": "BASE64"},
  "server_public_key": "BASE64",
  "session_id": "32_HEX_ZEICHEN"
}
```

Dieser reduzierte Vertrag gilt für den aktuellen Quellstand. Der unveränderte Release `v0.2.0-policy` liefert zusätzlich ältere Metadatenfelder; neue Clients ignorieren diese. Die API-Änderung erfordert vor einer Cluster-Umstellung ein neues Image samt neu erzeugter Policy und neuen Client-Referenzen. Alte Release-Dateien bleiben unverändert.

Der Client prüft die AMD-Zertifikatskette gegen seinen eigenen AMD-Vertrauensanker. Der binäre Report enthält die signierten Felder `MEASUREMENT`, `HOST_DATA` und `REPORT_DATA`. Letzteres muss genau den 64 ASCII-Hexzeichen von `SHA256(b"whisper-cpu-tee-v1\\0" + nonce + server_public_key + client_public_key + session_id)` entsprechen; die Schlüssel sind rohe unkomprimierte P-256-Punkte, die Nonce hat 32 Bytes und die Sitzungs-ID 16 Bytes. Die Antwort enthält keine zusätzliche `report_data`-Kopie, serverseitigen Prüfurteile, Softwareversionen oder GPU-Platzhalter. Die Sitzung läuft serverseitig nach 1800 Sekunden ab; der Client setzt zusätzlich sein eigenes Zeitlimit.

Release, Quellcommit, Paketversionen, Image-Digests und Modell-Dateihashes kommen aus separat vertrauenswürdig bezogenen Referenzdateien. Der externe Client muss deren Herkunft prüfen und das Release-Manifest mit seiner CPU-Prüfpolicy abgleichen, bevor er CPU-Versionen dem erfolgreich geprüften Image zuordnet. Ein Manifest ist eine überprüfbare Build-Beschreibung, kein eigener AMD-Nachweis; GPU-Ausführung und Modellnutzung bleiben ohne zusätzlichen Nachweis unbestätigt. Die Laufzeit-Images enthalten dieses Release-Manifest nicht. `/health` und `/v1/runtime` dienen nur der Betriebsinformation und liefern keinen Attestation-Nachweis.

CPU-Konfiguration: `GPU_URL` (GPU-API-Adresse), `AMD_KDS_ENABLED=true` für AMD-Zertifikate und optional `PORT` (Standard 8080). Die Attestation-Agent-API wird lokal im CPU-Gast unter `127.0.0.1:8006` erwartet. Der Betrieb in einem SEV-SNP-Gast und dessen Policy sind Aufgabe des externen Deployments. Die GPU benötigt genau eine zugewiesene CUDA-GPU. Das Modell liegt im Image unter `/opt/whisper-model`; beim Start werden die festgelegten Dateihashes geprüft. Zum Start werden keine Modelle oder Testaufnahmen aus dem Internet geladen.

## Build und unabhängiger Nachbau

```sh
python3 tools/build.py --version v0.2.0-dev --repeat
```

Mit `--repeat` werden beide Images zweimal gebaut und ihre Plattform-Digests verglichen; Abweichungen brechen den Build ab. Ein Aufruf ohne `--repeat` ist nur ein einzelner Entwicklungsbuild. Das Manifest enthält Commit, Datei-Hashes, Paketversionen, Modellrevision und Image-Digests. `build/inputs.json` enthält außerdem die vorhandene CPU-Gast-Referenz als Prüfwert; dieser Gast wird hier nicht selbst gebaut.

Der manuelle Release-Workflow läuft auf `sec-runner`, baut zweimal und veröffentlicht öffentliche Images unter `harbor.speeches.dev/library/whisper-confidential-{cpu,gpu}`, ohne deren Digests zu verändern. Ein hashgeprüfter Kata-3.32-Generator erzeugt anschließend `policy.rego`, `initdata.toml` und `attestation-policy.json`. Diese Dateien und das Manifest werden zunächst in einen privaten Release-Entwurf hochgeladen. Erst wenn alle Uploads einschließlich Dateigröße und SHA256 erfolgreich geprüft wurden, veröffentlicht die Pipeline den Stand automatisch als Vorabrelease. Fehlgeschlagene oder unvollständige Uploads bleiben unveröffentlicht. Die Veröffentlichung behauptet keinen erfolgreichen Hardwaretest; dieser Stand bleibt ein Prototyp mit ungeschützter GPU. Die festen [Prüfdateien und ihre Versionierung](verification/README.md) liegen zusätzlich im Repository. `policy/contract.json` ist der prüfbare API-Startvertrag, kein Cluster-Deployment. Build-/Policy-Werkzeuge landen nicht in den Laufzeit-Images. Policy-Erzeugung benötigt Python 3.14. Der Registry-Präfix steht in `build/inputs.json`; Zugangsdaten stammen ausschließlich aus dem Runner und werden nicht veröffentlicht.

Für einen Vergleich die genaue Manifest-Version und den Commit des Releases verwenden:

```sh
python3 tools/release.py verify --manifest /pfad/release-manifest.json \
  --cpu .build/dist/build-1/cpu.oci.tar --gpu .build/dist/build-1/gpu.oci.tar
```

Für direkte Dockerfile-Builds ist der passende benannte `wheels`-Kontext nötig; `tools/build.py` übernimmt dies. Die erzeugte `.build/build-info.json` wird ausschließlich von den Build-Werkzeugen zur Manifest-Erstellung verwendet und nicht in Images kopiert.

## Aktuelle Sicherheitsgrenze

CPU-Evidence und Sitzungsschlüssel werden bereitgestellt; der externe Client muss sie selbst prüfen. Für eine gebundene CPU-Anwendung muss das externe Deployment die unveränderte `initdata.toml` laden. Der Client vergleicht den signierten SNP-`HOST_DATA` mit dem aus einem vertrauenswürdig bezogenen Release stammenden Wert in `attestation-policy.json`. SHA256 bezieht sich auf die exakten unkomprimierten TOML-Bytes. Den Erwartungswert niemals einfach aus der Serverantwort übernehmen.

Die Policy bindet Image-Digest, Startbefehl, Umgebungswerte und schreibgeschütztes Root-Dateisystem. Nachträgliches Exec und Policy-Wechsel sind verboten. Beim erzwungenen Gast-Pull wird die konkrete Image-Quelle zusätzlich geprüft. Kopieren ist nur für begrenzte DNS-/Hostname-/K3s-Startdateien erlaubt, nicht für Anwendungscode oder Schlüssel. Generierte Dateien allein beweisen keine aktive Durchsetzung; das externe Deployment muss auch mit Negativtests geprüft werden.

Die GPU verarbeitet weiterhin Klartext ohne CC, und die CPU leitet Audio über HTTP an sie weiter. GPU-Attestation fehlt. Server-Metadaten werden nicht automatisch als verifiziert markiert; gleiche Image-Hashes allein beweisen nicht, welches Image der Cluster ausführt.
