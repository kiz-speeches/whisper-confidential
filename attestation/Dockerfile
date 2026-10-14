FROM golang:1.26.8-bookworm@sha256:dc9ad6c05acc7a88e5b71bde60a5fe3bd4b9f0db209011711b464107438a8107 AS verifier
WORKDIR /src
COPY attestation/verifier/ /src/
ENV GOTOOLCHAIN=local GOCACHE=/tmp/gocache
RUN GOOS=js GOARCH=wasm go build -buildvcs=false -trimpath -o /out/verifier.wasm . && cp /usr/local/go/lib/wasm/wasm_exec.js /out/wasm_exec.js
FROM python:3.12-bookworm@sha256:5560e9ab8709f459489e5b8aa696eda8a07ef821e14bb122be62d91234bfa98b
ARG SOURCE_DATE_EPOCH
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY attestation/requirements.lock /app/requirements.txt
RUN --mount=from=wheels,target=/wheels pip install --no-cache-dir --no-compile --no-index --find-links=/wheels --only-binary=:all: --require-hashes -r requirements.txt
COPY attestation/gateway.py attestation/evidence.py /app/
COPY static/ /app/static/
COPY --from=verifier /out/ /app/static/attestation/
USER 1000:1000
EXPOSE 8080
CMD ["python", "/app/gateway.py"]
