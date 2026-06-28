FROM python:3.11-slim

# Create a non-root user (HF Spaces requirement)
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Install dependencies first (better Docker layer caching)
COPY requirements.txt .
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
