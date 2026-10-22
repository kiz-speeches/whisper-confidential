# SelOSS V5 native CPU streaming

This release approves the private native-stateful W16 image named by digest in
attestation-policy.json. CPU guest, exact InitData (policy, CDH and AA), session
key and image are checked through AMD SEV-SNP. The native streaming state belongs
to the attested encrypted session; streams have ordered audio, bounded queues,
expiration and cancellation cleanup. Inference and weights remain inside the CPU
guest. The optional separate Qwen GPU is outside this ASR proof.

The model code, weights and container remain proprietary in a private registry.
These public files identify an approved binary; they do not make its source or
training independently auditable or reproducible. The repository maintainers
remain the authority approving the image and administratively recorded guest
measurement. A hash is not proof of program correctness.

The browser computes SHA-256 of initdata.toml and matches signed HOST_DATA,
checks embedded policy/CDH/AA bytes and their hashes, and checks the exact image
digest in the enforced policy. Stream operations use separate authenticated
request/response data domains, share replay protection with WAV requests, and
never expose the original unauthenticated native model endpoints.
