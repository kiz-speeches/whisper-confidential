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

Der Build setzt einen sauberen Commit voraus und lädt ausschließlich hashgeprüfte Wheels. CPU- und GPU-Image werden mit festen Eingaben zweimal ohne Layer-Cache gebaut. Nur bei identischen Plattform-Digests entstehen `.build/dist/release-manifest.json` und `SHA256SUMS`. Das Manifest enthält Commit, Datei-Hashes, Paketversionen, Modellrevision und Image-Digests. `build/inputs.json` enthält außerdem die vorhandene CPU-Gast-Referenz als Prüfwert; dieser Gast wird hier nicht selbst gebaut. Der manuelle GitHub-Workflow hängt Manifest und Prüfsummen an einen Release-Entwurf. Für einen Vergleich die genaue Manifest-Version und den Commit des Releases verwenden:

```sh
python3 tools/release.py verify --manifest /pfad/release-manifest.json \
  --cpu .build/dist/build-1/cpu.oci.tar --gpu .build/dist/build-1/gpu.oci.tar
```

Für direkte Dockerfile-Builds sind außerdem die erzeugte `.build/build-info.json` und der passende benannte `wheels`-Kontext nötig; `tools/build.py` übernimmt beides.

## Aktuelle Sicherheitsgrenze

CPU-Evidence und Sitzungsschlüssel werden bereitgestellt; der externe Client muss sie selbst prüfen. Die GPU verarbeitet derzeit Klartext ohne CC, und die CPU leitet Audio über HTTP an sie weiter. Durchgesetzte Anwendungspolicy, HOST_DATA-Bindung und GPU-Attestation fehlen weiterhin. Release-Metadaten sind ausdrücklich nicht attestiert. Gleiche Image-Hashes beweisen noch nicht, welches Image der Cluster ausführt. GHCR-Veröffentlichung und Deployment werden separat eingerichtet.
