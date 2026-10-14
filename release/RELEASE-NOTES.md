Reproduzierbarer Prototyp-Build von CPU-Gateway und GPU-Whisper-Worker für Linux AMD64.

`release-manifest.json` enthält den gebauten Git-Commit, Quellbaum- und Datei-Hashes, feste Paketversionen, Modellrevision und Dateihashes, Policy-Entwurf und CPU-Gast-Referenzen sowie die Plattform-Digests beider Images. Beide Images werden zweimal ohne Layer-Cache gebaut; nur bei identischen Digests entstehen die Release-Artefakte.

Nachbau und Vergleich sind in `release/README.md` beschrieben. Die angehängten Dateien enthalten keine Signatur und keinen Nachweis, dass der laufende Cluster diese Images ausführt. CPU-Attestation prüft den Gast und Sitzungsschlüssel. Anwendungspolicy/HOST_DATA-Bindung, attestierte Anwendungsversionen und GPU-Attestation sind noch offen. Die normale GPU verarbeitet Klartext; diese Version bietet keinen vollständigen Schutz vor dem Betreiber.
