FROM python:3.12-slim-bookworm

WORKDIR /app

# Upgrade all system packages first to patch known CVEs in the base image,
# then install only the runtime dep pdfplumber needs (libpoppler-cpp-dev).
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p backend/resumes backend/storage logs

ENV PYTHONUNBUFFERED=1
# DB_PATH is only used when DATABASE_URL is not set (local dev / SQLite fallback)
ENV DB_PATH=backend/storage/jobs.db

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
