# Multi-stage Dockerfile for MediClaim-AI

# Stage 1: Build React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python Backend
FROM python:3.11-slim AS runtime

# Install system dependencies (Poppler for PDF rendering, Tesseract for OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install production Python dependencies (excluding Ragas / DeepEval judges)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    uvicorn[standard] \
    python-multipart \
    google-genai \
    langfuse \
    pytesseract \
    pillow \
    -r requirements.txt

# Pre-download HuggingFace models at build time so runtime requires zero model downloads
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
    SentenceTransformer('BAAI/bge-small-en-v1.5'); \
    CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy application source code and pre-processed policy data
COPY src/ ./src/
COPY data/processed/ ./data/processed/
COPY data/qdrant/ ./data/qdrant/

# Copy built frontend assets from Stage 1
COPY --from=frontend-builder /build/dist ./frontend/dist

# Set runtime environment
ENV PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    CLAIM_LLM_MODEL=gemini-3.1-flash-lite

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
