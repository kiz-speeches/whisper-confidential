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

CPU-Konfiguration: `GPU_URL` (GPU-API-Adresse), `AMD_KDS_ENABLED=true` für AMD-Zertifikate und optional `PORT` (Standard 8080). Die Attestation-Agent-API wird lokal im CPU-Gast unter `127.0.0.1:8006` erwartet. Der Betrieb in einem SEV-SNP-Gast und dessen Policy sind Aufgabe des externen Deployments. Die GPU benötigt genau eine zugewiesene CUDA-GPU. Das Modell liegt im Image unter `/opt/whisper-model`; beim Start werden die festgelegten Dateihashes geprüft. Zum Start werden keine Modelle oder Testaufnahmen aus dem Internet geladen.

## Build und unabhängiger Nachbau

```sh
python3 tools/build.py --version v0.2.0-dev --repeat
```

Mit `--repeat` werden beide Images zweimal gebaut und ihre Plattform-Digests verglichen; Abweichungen brechen den Build ab. Ein Aufruf ohne `--repeat` ist nur ein einzelner Entwicklungsbuild. Das Manifest enthält Commit, Datei-Hashes, Paketversionen, Modellrevision und Image-Digests. `build/inputs.json` enthält außerdem die vorhandene CPU-Gast-Referenz als Prüfwert; dieser Gast wird hier nicht selbst gebaut.

Der manuelle Release-Workflow läuft auf `sec-runner`, baut zweimal und veröffentlicht öffentliche Images unter `harbor.speeches.dev/library/whisper-confidential-{cpu,gpu}`, ohne deren Digests zu verändern. Ein hashgeprüfter Kata-3.32-Generator erzeugt anschließend `policy.rego`, `initdata.toml` und `attestation-policy.json`. Diese Dateien und das Manifest werden an einen privaten Release-Entwurf angehängt. `policy/contract.json` ist der prüfbare API-Startvertrag, kein Cluster-Deployment. Build-/Policy-Werkzeuge landen nicht in den Laufzeit-Images. Policy-Erzeugung benötigt Python 3.14. Der Registry-Präfix steht in `build/inputs.json`; Zugangsdaten stammen ausschließlich aus dem Runner und werden nicht veröffentlicht.

Für einen Vergleich die genaue Manifest-Version und den Commit des Releases verwenden:

```sh
python3 tools/release.py verify --manifest /pfad/release-manifest.json \
  --cpu .build/dist/build-1/cpu.oci.tar --gpu .build/dist/build-1/gpu.oci.tar
```

Für direkte Dockerfile-Builds sind außerdem die erzeugte `.build/build-info.json` und der passende benannte `wheels`-Kontext nötig; `tools/build.py` übernimmt beides.

## Aktuelle Sicherheitsgrenze

CPU-Evidence und Sitzungsschlüssel werden bereitgestellt; der externe Client muss sie selbst prüfen. Für eine gebundene CPU-Anwendung muss das externe Deployment die unveränderte `initdata.toml` laden. Der Client vergleicht den signierten SNP-`HOST_DATA` mit dem aus einem vertrauenswürdig bezogenen Release stammenden Wert in `attestation-policy.json`. SHA256 bezieht sich auf die exakten unkomprimierten TOML-Bytes. Den Erwartungswert niemals einfach aus der Serverantwort übernehmen.

Die Policy bindet Image-Digest, Startbefehl, Umgebungswerte und schreibgeschütztes Root-Dateisystem. Nachträgliches Exec und Policy-Wechsel sind verboten. Beim erzwungenen Gast-Pull wird die konkrete Image-Quelle zusätzlich geprüft. Kopieren ist nur für begrenzte DNS-/Hostname-/K3s-Startdateien erlaubt, nicht für Anwendungscode oder Schlüssel. Generierte Dateien allein beweisen keine aktive Durchsetzung; das externe Deployment muss auch mit Negativtests geprüft werden.

Die GPU verarbeitet weiterhin Klartext ohne CC, und die CPU leitet Audio über HTTP an sie weiter. GPU-Attestation fehlt. Server-Metadaten werden nicht automatisch als verifiziert markiert; gleiche Image-Hashes allein beweisen nicht, welches Image der Cluster ausführt.
