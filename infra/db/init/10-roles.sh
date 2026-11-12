#!/usr/bin/env bash
# Roles de base de datos de Trulab Viajes (S1-04, docs/database-design.md §6).
#
# Crea o actualiza, con privilegios mínimos:
#   - trulab_owner: dueño de la BD y del esquema `public`; ejecuta las migraciones de Alembic.
#                   No es superusuario ni crea roles o bases de datos.
#   - trulab_app:   rol de la API. Solo CONNECT; el resto (USAGE del esquema y DML sobre las
#                   tablas) lo concede la migración inicial. Sin BYPASSRLS y sin ser dueño de nada.
#
# Lo ejecuta un superusuario (o un administrador con CREATEROLE en un PostgreSQL gestionado):
#   - En Docker, solo la primera vez, cuando el volumen está vacío (docker-entrypoint-initdb.d).
#   - A mano, para aplicarlo sobre un volumen existente o tras cambiar una contraseña:
#       docker compose exec db bash /docker-entrypoint-initdb.d/10-roles.sh
# Es idempotente: crear los roles solo si faltan y reaplicar atributos y contraseñas.
#
# Los roles no van en Alembic: son objetos del clúster (no de la BD) y llevan contraseñas.
# Extensiones y privilegios del esquema sí van en Alembic (backend/alembic/versions/).

set -Eeo pipefail

: "${POSTGRES_USER:?Falta POSTGRES_USER}"
: "${POSTGRES_DB:?Falta POSTGRES_DB}"
OWNER_DB_USER="${OWNER_DB_USER:-trulab_owner}"
APP_DB_USER="${APP_DB_USER:-trulab_app}"
: "${OWNER_DB_PASSWORD:?Defina OWNER_DB_PASSWORD en .env}"
: "${APP_DB_PASSWORD:?Defina APP_DB_PASSWORD en .env}"

if [ "$OWNER_DB_USER" = "$POSTGRES_USER" ] || [ "$APP_DB_USER" = "$POSTGRES_USER" ]; then
    echo "10-roles.sh: POSTGRES_USER ($POSTGRES_USER) es el superusuario de arranque;" \
         "debe ser distinto de $OWNER_DB_USER y $APP_DB_USER." >&2
    exit 1
fi

# Las contraseñas viajan como variables de psql y se citan con %L/:'var' (sin inyección SQL).
# No se registran: \gexec no imprime las sentencias que ejecuta.
psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v db="$POSTGRES_DB" \
    -v owner="$OWNER_DB_USER" -v owner_password="$OWNER_DB_PASSWORD" \
    -v app="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" <<'SQL'
-- 1. Roles (solo si no existen).
SELECT format('CREATE ROLE %I', :'owner')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'owner') \gexec
SELECT format('CREATE ROLE %I', :'app')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec

-- 2. Atributos y contraseña (siempre: corrige derivas y permite rotar contraseñas).
SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'owner', :'owner_password') \gexec
SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'app', :'app_password') \gexec

-- 3. Base de datos: trulab_owner es el dueño (en PG 15+ eso lo hace dueño de `public`, que
--    pertenece a pg_database_owner). Solo los roles de la aplicación pueden conectarse.
ALTER DATABASE :"db" OWNER TO :"owner";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"app";
SQL

echo "10-roles.sh: roles $OWNER_DB_USER y $APP_DB_USER listos en la BD $POSTGRES_DB."
