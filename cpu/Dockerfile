FROM python:3.12-bookworm@sha256:5560e9ab8709f459489e5b8aa696eda8a07ef821e14bb122be62d91234bfa98b
ARG SOURCE_DATE_EPOCH
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
LABEL org.opencontainers.image.source="https://github.com/kiz-speeches/whisper-confidential"
COPY cpu/requirements.lock /tmp/requirements.lock
RUN --mount=from=wheels,target=/wheels pip install --no-cache-dir --no-compile --no-index --find-links=/wheels --only-binary=:all: --require-hashes -r /tmp/requirements.lock
COPY cpu/api.py cpu/evidence.py /app/
USER 1000:1000
EXPOSE 8080
CMD ["python", "/app/api.py"]
