FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt python-multipart

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Data directory for SQLite DB (mount as volume)
VOLUME /app/data

ENV JOB_AGENT_DB=/app/data/jobs.db

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
