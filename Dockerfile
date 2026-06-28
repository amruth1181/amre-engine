FROM python:3.11-slim

# Create a non-root user (HF Spaces requirement)
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Install dependencies first (better Docker layer caching).
# Install the CPU-ONLY torch from the PyTorch CPU index BEFORE the rest — the
# default PyPI wheel ships CUDA (~2.5GB) and blows the free CPU Space's limits.
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite persistent storage
RUN mkdir -p /data && chown user:user /data

# Switch to non-root user
USER user

# HF Spaces expects port 7860
EXPOSE 7860

# Start the FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
