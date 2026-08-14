docker compose -f docker-compose.local.yml up -d
Write-Host "Waiting for services to become healthy..."
Start-Sleep -Seconds 10
Write-Host "Starting Frontend (Nginx static proxy)..."
docker run -d -p 8080:80 --name abast-frontend nginx:alpine
Start-Process "http://localhost:8080"
