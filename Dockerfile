# One image for Django, the Celery worker and the FastAPI LLM service.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app
COPY requirements.txt requirements.txt
COPY llm_service/requirements.txt llm_service/requirements.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt -r llm_service/requirements.txt

COPY . .

EXPOSE 8000 8001
