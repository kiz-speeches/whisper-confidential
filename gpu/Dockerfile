FROM python:3.12-bookworm@sha256:5560e9ab8709f459489e5b8aa696eda8a07ef821e14bb122be62d91234bfa98b AS dependencies
ARG SOURCE_DATE_EPOCH
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY gpu/requirements.lock /tmp/requirements.lock
RUN --mount=from=wheels,target=/wheels pip install --no-cache-dir --no-compile --no-index --find-links=/wheels --only-binary=:all: --require-hashes -r /tmp/requirements.lock

FROM dependencies AS model
ENV HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
COPY build/inputs.json /build/inputs.json
COPY gpu/prepare_model.py /build/prepare_model.py
RUN python /build/prepare_model.py

FROM dependencies
LABEL org.opencontainers.image.source="https://github.com/kiz-speeches/whisper-confidential"
ENV NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    WHISPER_MODEL_PATH=/opt/whisper-model \
    LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib
COPY --from=model /opt/whisper-model/ /opt/whisper-model/
COPY --from=model /opt/model-inputs.json /app/model-inputs.json
COPY gpu/api.py gpu/verify_model.py /app/
USER 1000:1000
EXPOSE 8080
CMD ["python", "/app/api.py"]
