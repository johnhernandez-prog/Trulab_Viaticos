# scripts/

Utilidades fuera de la API.

- `crear_env.py`: crea el `.env` local desde `.env.example` con contraseñas aleatorias y distintas para `postgres`, `trulab_owner` y `trulab_app` (también en `DATABASE_URL*`). No sobrescribe un `.env` existente salvo con `--forzar`. Lo usan la CI y el equipo: `python scripts/crear_env.py` (en Windows, `.venv\Scripts\python scripts\crear_env.py`).
- `etl_appsheet/`: migración única de datos históricos desde AppSheet (RF-012, tarea S3-06).
