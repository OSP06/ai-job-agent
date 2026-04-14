FROM python:3.12-slim

WORKDIR /app

# System deps for pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runtime dirs (Railway mounts /data as a persistent volume)
RUN mkdir -p backend/resumes backend/storage logs

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/jobs.db
ENV RESUMES_DIR=/data/resumes

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
