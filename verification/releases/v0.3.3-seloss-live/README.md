# SelOSS V5 live CPU inference · v0.3.3-seloss-live

This release approves one private CPU image for AMD SEV-SNP inference.
The image implements separate 80 ms and 1,280 ms incremental ASR windows;
window size is not a claim of word latency or recognition accuracy.
The refinement retains the original W16 context for confirmed text.
Both lane states belong to the authenticated encrypted session. The final
canonical transcript is published only after both workers have stopped.

- CPU image: `harbor.speeches.dev/private-inference/asr-v5-cpu-tee@sha256:f0bf81d475be104a8f03de9f9efc3ad9dd15ada827051aebc71c32d807aa14bb`
- SNP HOST_DATA: `c5dae9ffed1c7f98f81741e81cd5008f56d421a1e05f6dec5490554d428e7065`
- Policy SHA-256: `8232be7bc23ddc9977201b8522397d3e8593f85669934e6730b642dd8090243e`

Verify the original AMD report and its fresh session-key binding, then match
MEASUREMENT and HOST_DATA through `verification/accepted.json` at one fixed
repository commit. Hash the exact InitData bytes, verify its embedded policy,
CDH/AA configuration and the policy-pinned image digest. Policy enforcement
belongs to the measured guest; these public metadata files are not an AMD
signature by themselves.

ASR runs entirely on the CPU in the guest, including the bundled private model.
No GPU is required for ASR. The separate Qwen GPU service remains unattested.
The model, tokenizer, original proprietary sources and image layers are private;
this repository does not provide a public reproducible build of that image.
The existing guest measurement is administrator-recorded, not an independently
reproduced guest-build claim. Approval trusts the repository maintainers.

The registry-reader resource name and broker certificate are public pins.
No registry password, private key, model weight, audio or transcript is published.
