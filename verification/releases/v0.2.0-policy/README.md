# v0.2.0-policy: feste Prüfdateien

Diese Dateien gehören zu den bereits gebauten Images aus dem Quellcommit [`920aaa1cf3692a6c0a512178c34fe762443af869`](https://github.com/kiz-speeches/whisper-confidential/tree/920aaa1cf3692a6c0a512178c34fe762443af869). Sie wurden erst nach dem Build in einem neuen Repository-Commit abgelegt. Dadurch ändern sich weder der Quellcommit noch die vorhandenen Image-Digests oder der Release-Tag. GitHub-Links benötigen Zugriff auf das private Repository.

| Datei | Bedeutung |
| --- | --- |
| [release-manifest.json](release-manifest.json) | Quellcommit, Quelldateihashes, feste Build-Eingaben, Paketversionen und beide Image-Digests. |
| [attestation-policy.json](attestation-policy.json) | Erwartete Gastmessung, `HOST_DATA`, CPU-Image-Digest und Umfang der Prüfung. Diese Werte muss der Client unabhängig vom Server beziehen. |
| [policy.rego](policy.rego) | Tatsächlich gehärtete CPU-Gast-Policy mit Image- und Startvorgaben. |
| [initdata.toml](initdata.toml) | Exakte InitData-Bytes einschließlich der gehärteten Policy. Deren SHA256 muss dem signierten `HOST_DATA` entsprechen. |
| [hardware-validation.json](hardware-validation.json) | Zusammenfassung der durchgeführten Tests vom 14. Oktober 2026. Dokumentation, kein kryptografischer Laufzeitnachweis. |
| [SHA256SUMS](SHA256SUMS) | Prüfsummen der fünf Dateien in diesem Snapshot. |

Die ersten vier Dateien sind bytegleich mit den ursprünglichen Release-Assets. Die ursprüngliche Release-Prüfsummenliste enthielt zusätzlich Generator-Zwischendaten; die Liste hier enthält stattdessen die vier Prüfdateien und die spätere Testzusammenfassung. `policy-input.json` aus dem Release ist eine vom Generator umgeschriebene Zwischenstufe mit einer noch ungehärteten Policy-Annotation und darf nicht als verbindliche Policy verwendet werden. Verbindlich sind `policy.rego` und die exakten Bytes der hier abgelegten `initdata.toml`.

Im heruntergeladenen Snapshot-Verzeichnis prüfen:

```sh
sha256sum -c SHA256SUMS
```

Eine gemeinsam mit manipulierten Dateien ausgetauschte Prüfsummenliste schafft kein Vertrauen. Dafür benötigt man den unabhängig bezogenen vollständigen Repository-Commit oder eine anderweitig vertrauenswürdige Referenz. Für diesen Release gilt:

```text
Quellcommit:          920aaa1cf3692a6c0a512178c34fe762443af869
CPU-Image SHA256:    f8167403f3524267e62e9127aab4546d13f7beb3d38b7f8adf9094864de19752
GPU-Image SHA256:    f34537084c07f07c74197a8402fc2614c5560b61db0294cad74a308f8ce58ed2
Policy SHA256:       5a85e510606ff97db323394acf71bc40cbbea7e3ba2eac41970029027d68d8ee
InitData / HOST_DATA:a2966d8c4d42ffb11af7eaae8c10e8a31874c764934a59e514485e08fffca024
```

Der lokal geprüfte AMD-Bericht bindet die erwartete Gastmessung und diesen `HOST_DATA`. Die InitData enthält die Policy; diese erlaubt genau das CPU-Image mit seinem Digest und dem festgelegten Startvertrag. Der Bericht bindet außerdem den Sitzungsschlüssel an die aktuelle Anfrage. Die Grenzen der Zusage stehen in der [Übersicht](../../README.md).

Die Modellgewichte sind bereits in [`build/inputs.json` des Quellcommits](https://github.com/kiz-speeches/whisper-confidential/blob/920aaa1cf3692a6c0a512178c34fe762443af869/build/inputs.json) auf die Hugging-Face-Revision `536b0662742c02347bc0e980a01041f333bce120` und vier SHA256-Dateihashes festgelegt. Sie werden beim Build und GPU-Start geprüft und liegen im GPU-Image. Diese Bindung beschreibt das veröffentlichte Image; ohne GPU-Attestation ist die aktive Ausführung genau dieser Gewichte von außen noch nicht nachgewiesen.
