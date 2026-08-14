FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache libpq-dev gcc musl-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Use a non-root user for security
RUN adduser -D exporteruser
USER exporteruser

EXPOSE 8000

CMD ["python", "main.py"]
