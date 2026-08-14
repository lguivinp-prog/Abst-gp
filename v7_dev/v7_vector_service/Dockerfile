FROM python:3.11-slim

WORKDIR /app

# Required for psycopg2-binary to compile/link if necessary, though -binary usually is fine on linux
RUN apt-get update && apt-get install -y libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
