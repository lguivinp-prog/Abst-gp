# Abast-gp V6 - Institutional Deployment Framework

## 1. Modelo de Despliegue Multi-Entidad (On-Premises Segregado)
Debido a regulaciones del Estado, la versión V6.0.1 se despliega físicamente en servidores locales por entidad (Ministerio, Gobierno Regional). 
- **Separación de Entidades**: Aislamiento total vía instancias separadas de Docker Compose.
- **Configuración Inicial**: Se inyectan las claves PIDE (SUNAT/RNP) y contraseñas de BD en un `.env` generado in-situ por el Administrador de TI local.

## 2. Onboarding Institucional
1. Inspección de Hardware Local (32GB RAM min, Storage SSD NVMe).
2. Capacitación de "Train the Trainers" (Jefes Logísticos).
3. Habilitación de URLs internas (ej. `http://abast.oficina.gob.pe`).

## 3. Support Model (SLA)
- **Nivel 1 (Helpdesk Institucional)**: Resuelve problemas de login (RBAC), olvido de contraseñas, o re-entrenamiento sobre uso del escáner por rechazos de calidad (`QUALITY_BLOCKED`).
- **Nivel 2 (SRE Abast-gp Local)**: Reinicio de contenedores Celery (OCR Workers bloqueados), revisión de caídas de Base de Datos, recuperación de Backups `pg_dump`.
- **Nivel 3 (Arquitectura Abast-gp)**: Corrección de *Bugs* en código (Python/RAG), optimización algorítmica de Chunks, parches de seguridad Docker.

## 4. Comercialización y Propuesta de Valor (Pre-SaaS)
**Propuesta de Valor:** "El único software de Abastecimiento Estatal impulsado por IA que NO decide, asegurando 100% de cumplimiento legal ante Contraloría, reduciendo tiempos en 30%".
**Paquete:** `Abast-gp Enterprise On-Prem Node` (Licencia perpetua + Mantenimiento Nivel 3).
