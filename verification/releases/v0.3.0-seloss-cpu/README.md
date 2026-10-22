# Private CPU ASR V5

These public verification files describe the approved AMD SNP guest and its private, digest-pinned ASR image. The image includes the API and the proprietary model; source code, weights, tokenizers and registry credentials are not published here.

`HOST_DATA` is the SHA-256 of the exact `initdata.toml` bytes. That document contains the Kata policy, the Confidential Data Hub configuration and the Attestation Agent configuration. The client checks all three and matches the image digest in the hardened policy. The public KBS certificate authenticates the private image-credential service; it is not a registry password.

The model is CPU-only and runs in the same guest as the encrypted API. A separate GPU is still used by the dictation application's Qwen text editor.

A matching container digest establishes the approved binary identity. Proprietary source and model weights cannot be independently audited or rebuilt from these public files. Approval of this binary still depends on the repository maintainers.

Run `sha256sum --check SHA256SUMS` to check these files locally.
