# Release und unabhängiger Nachbau

Ein Release verbindet Quellcode, feste Build-Eingaben und Image-Inhalt. Hardware-Attestation ist ein zusätzlicher Schritt: Ein korrekt gebautes Image beweist noch nicht, dass der Server genau dieses Image ausführt.

`inputs.json` enthält festgelegte Basisimages, Go-Compiler, BuildKit-Builder, die genaue Whisper-Modellrevision und SHA256 für jede Modelldatei. Die Python-Locks umfassen alle Abhängigkeiten und die konkreten Wheels für Python 3.12/Linux AMD64. Der Build lädt nur Dateien, die zu diesen Hashes passen. Die gemessene CPU-Gast-Referenz und ihre Firmware-/Kernel-/Gastimage-Hashes sind separat erfasst; diese vorhandenen VM-Artefakte werden in diesem Repo nicht aus ihren ursprünglichen Quellen neu gebaut.

In einem sauberen Checkout:

```sh
python3 tools/build.py --version v0.1.0 --repeat
```

Das baut CPU-Gateway und GPU-Worker zweimal ohne Layer-Cache mit derselben festgelegten BuildKit-Version. Der Ablauf setzt `SOURCE_DATE_EPOCH` auf die Commit-Zeit und normalisiert Exportzeitstempel. Die Prüfung vergleicht die OCI-Plattform-Manifeste. Ausführungszeit und Signaturen späterer Provenance-Dokumente gehören nicht in diesen Vergleich. Derselbe Quellcode allein garantiert keine gleichen Digests; Gleichheit wird tatsächlich geprüft, und eine Abweichung bricht den Build ab.

Vorher werden fehlende Wheels einmal hashgeprüft nach `release/wheels/` geladen und als benannter Build-Kontext eingebunden. Beide Image-Builds installieren dann offline aus diesen festen Eingabedateien. Die Dockerfiles werden über `tools/build.py` aufgerufen; ein direkter Dockerfile-Aufruf benötigt zusätzlich den passenden `--build-context wheels=...` und die erzeugte `static/build-info.json`.

Ausgaben unter `release/dist/`:

- `release-manifest.json`: Git-Commit, Quellbaumhash und Datei-Hashes, Paketversionen, Modell-/Policy-/Gast-Referenzen sowie Digests der gebauten Images.
- `SHA256SUMS`: Transportprüfsummen der erzeugten Manifest- und Archivdateien.
- `build-1/*.oci.tar` und `build-2/*.oci.tar`: lokal gebaute Images.

Einen eigenen Nachbau mit einem separat bezogenen Release-Manifest vergleichen:

```sh
python3 tools/release.py verify --manifest /pfad/zum/release-manifest.json \
  --cpu release/dist/build-1/cpu.oci.tar --gpu release/dist/build-1/gpu.oci.tar
```

Die Image-Prüfung kontrolliert die Digests der referenzierten Konfiguration und jedes Layers. Die SHA256 einer gesamten Tar-Datei dient der Transportprüfung; für den unabhängigen Nachbau wird der Plattform-Image-Digest verglichen, weil Archivverpackung abweichen kann.

Die Workflow-Datei `release.yml` kann über GitHub Actions manuell gestartet werden und lädt Manifest und Checksums als Workflow-Artefakt hoch. Sie veröffentlicht noch keine Images und erzeugt kein öffentliches Release. Registry-Ziel, Release-Signierung/Vertrauensanker und die Zuordnung zu einem Release-Tag müssen vor Veröffentlichung bewusst ergänzt werden. Ein Workflow-Artefakt allein ist kein unabhängig signierter Software-Release.

## Was für attestierte Anwendungsversionen noch fehlt

1. Die gebauten Images in eine Registry veröffentlichen und im Deployment per Digest verwenden. Die derzeitige Source-ConfigMap-/Startinstallation ist weiterhin ein Entwicklungsdeployment.
2. Eine tatsächlich durchgesetzte Kata-Agent-Policy erzeugen und prüfen: genau diese Image-Digests, Befehle, Umgebungswerte und erlaubten Mounts; keine nachträglichen Exec-/Copy-/Codeänderungen. `policies/workload-intent.json` beschreibt das Ziel, ist **keine ausgeführte Policy**.
3. Diese Policy zusammen mit AA/CDH-Konfiguration als Init-Data in `HOST_DATA` binden. Der Client muss den erwarteten Wert aus dem vertrauenswürdig bezogenen Release-Manifest vergleichen; der gemessene Gast muss die gebundene Konfiguration selbst prüfen.
4. Die eingebaute Modell-Dateiprüfung beim Laufzeitstart durch eine Policy absichern, die Austausch des Prüfers, andere Modellpfade und veränderliche Modell-Mounts verhindert. Der neue gebaute GPU-Worker prüft Modell-Dateihashes beim Build und beim Start; der bisherige live laufende Entwicklungsworker wurde dafür noch nicht ersetzt.
5. CPU-/GPU-Endpunkte und geschützten Transport gemeinsam binden. GPU-Attestation bleibt momentan ein leerer Platzhalter; normale HTTP-Weitergabe zur GPU schützt keine Audiodaten vor dem Betreiber.
6. Positiv- und Negativtests auf echter Hardware: falsches Image, falsche Policy, andere Konfiguration/Modellgewichte und Betreiber-Exec müssen scheitern. Erst danach dürfen Anwendungs-/Versionsfelder als verifiziert gelten.

Die Reportanzeige übernimmt Versionen und Hashes aus `static/build-info.json` aktuell als **Serverangaben, nicht attestiert**. `software_release.verified` und `workload_policy_verified` bleiben false. CPU-Report, Schlüsselbindung und AMD-Verifikation werden dadurch nicht abgeschwächt.

## Lokal bezogener Browser-Client

```sh
bash attestation/build.sh
python3 tools/client.py --server https://whisper.speeches.dev --port 8780
```

Danach `http://127.0.0.1:8780` öffnen. HTML, JavaScript, WASM und Referenzpolicy kommen aus dem lokalen Checkout. Nur die vier ausdrücklich erlaubten Prototype-API-Pfade werden über geprüftes HTTPS zum Server weitergeleitet. Der Server liefert keinen Browser-Code und keinen Referenzmesswert an diesen Client. Vertrauen in den bezogenen Repo-/Release-Stand und den lokalen Rechner bleibt notwendig. Der Client hat derzeit dieselben offenen Workload-/GPU-Grenzen wie die öffentliche Seite.

Quellen: [CoCo Init-Data](https://confidentialcontainers.org/docs/features/initdata/), [Kata genpolicy](https://github.com/kata-containers/kata-containers/tree/main/src/tools/genpolicy), [Docker reproducible builds](https://docs.docker.com/build/ci/github-actions/reproducible-builds/).
