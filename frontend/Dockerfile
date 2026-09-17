# Base para desarrollo y build
FROM node:20-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps

COPY . .
RUN npm run build

# Servidor estático ligero para producción (Nginx)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Configuración para soportar react-router (SPA)
RUN echo 'server { \
    listen 80; \
    client_max_body_size 10M; \
    resolver 127.0.0.11 valid=5s; \
    set $api_upstream api:8000; \
    location /auth/ { \
        proxy_pass http://$api_upstream; \
        proxy_set_header Host $host; \
    } \
    location /api/ { \
        proxy_pass http://$api_upstream; \
        proxy_set_header Host $host; \
    } \
    location /cases/ { \
        proxy_pass http://$api_upstream; \
        proxy_set_header Host $host; \
    } \
    location / { \
        root   /usr/share/nginx/html; \
        index  index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
