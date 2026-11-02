# SelOSS V5 live CPU inference · v0.3.2-seloss-live

This release approves one private CPU image for AMD SEV-SNP inference.
The image implements separate 80 ms and 960 ms incremental ASR windows;
window size is not a claim of word latency or recognition accuracy.
Both lane states belong to the authenticated encrypted session. The final
canonical transcript is published only after both workers have stopped.

- CPU image: `harbor.speeches.dev/private-inference/asr-v5-cpu-tee@sha256:b5e4282efff3a63904b9b64334c66766adb9294bea5069b72719b27ce1c2e7f5`
- SNP HOST_DATA: `2844e2d22421cb4b321948f18ad4a96af9d0e0dba16806a1ef1603c578e09386`
- Policy SHA-256: `9f16dec58b3ff6d793f19e82ce3d43de6dc898a145afcb3d8070137ea01e1b62`

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
