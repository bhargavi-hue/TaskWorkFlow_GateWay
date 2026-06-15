FROM python:3.11-slim

# Install system dependencies for building psycopg2 if needed
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install added dependencies
RUN pip install --no-cache-dir sqlalchemy pymongo psycopg2-binary pyjwt sentence-transformers numpy python-dotenv

COPY . .

EXPOSE 8000

CMD ["python", "run.py"]