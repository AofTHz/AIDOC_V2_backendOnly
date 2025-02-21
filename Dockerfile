# Use a smaller Python image (instead of Miniconda)
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies (Poppler & Tesseract for OCR)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*


# Copy application code
COPY . /app

# Copy and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt


# Expose FastAPI port (5000, as set in `main.py`)
EXPOSE 5000

# Run FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
