FROM python:3.9-slim

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install OCR Libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    doctr \
    # Create app directory \
    WORKDIR /app

# Install Python dependencies first (cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source code
COPY . .

# Expose port (sesuaikan dengan aplikasi kamu)
EXPOSE 8000

# Start command (ubah ke FastAPI/Streamlit/Flask sesuai projectmu)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"