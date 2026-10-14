# Base image used by the verified running prototype, pinned to its actual digest.
FROM python:3.12-bookworm@sha256:5560e9ab8709f459489e5b8aa696eda8a07ef821e14bb122be62d91234bfa98b
ARG SOURCE_DATE_EPOCH
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    WHISPER_MODEL_PATH=/opt/whisper-model WHISPER_SMOKE_AUDIO=/opt/whisper-model/jfk.flac \
    LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib
WORKDIR /app
COPY release/gpu-requirements.lock /app/requirements.lock
RUN --mount=from=wheels,target=/wheels pip install --no-cache-dir --no-compile --no-index --find-links=/wheels --only-binary=:all: --require-hashes -r requirements.lock
COPY release/inputs.json /app/release/inputs.json
COPY tests/fixtures/jfk.flac /app/tests/fixtures/jfk.flac
COPY prepare_model.py /app/prepare_model.py
RUN python prepare_model.py
COPY app.py /app/app.py
COPY verify_model.py /app/verify_model.py
COPY static /app/static
USER 1000:1000
EXPOSE 8080
CMD ["python", "/app/app.py"]
