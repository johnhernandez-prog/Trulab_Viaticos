"""Crea el `.env` local a partir de `.env.example` con contraseñas aleatorias para la BD.

Uso (desde la raíz del repositorio):
    python scripts/crear_env.py            # no sobrescribe un .env existente
    python scripts/crear_env.py --forzar   # lo reemplaza (las contraseñas cambian: ver abajo)

Genera POSTGRES_PASSWORD, OWNER_DB_PASSWORD y APP_DB_PASSWORD (distintas) y las pone también en
DATABASE_URL_MIGRATIONS y DATABASE_URL. El resto de variables queda como en `.env.example`.
Lo usan la CI (S1-06) y el equipo para el entorno local. Si se reemplaza el .env de un volumen de
BD ya creado, hay que recrear el volumen (`docker compose down -v`) o reaplicar
`infra/db/init/10-roles.sh` (ver infra/README.md).

Solo usa la librería estándar. Nunca imprime las contraseñas.
"""

import argparse
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLA = RAIZ / ".env.example"
DESTINO = RAIZ / ".env"

CONTRASENAS = ("POSTGRES_PASSWORD", "OWNER_DB_PASSWORD", "APP_DB_PASSWORD")
# Rol de cada URL de conexión → variable con su contraseña.
URLS = {"trulab_owner": "OWNER_DB_PASSWORD", "trulab_app": "APP_DB_PASSWORD"}


def generar(plantilla: str) -> str:
    valores = {nombre: secrets.token_urlsafe(24) for nombre in CONTRASENAS}
    lineas = []
    for linea in plantilla.splitlines():
        nombre = linea.split("=", 1)[0]
        if nombre in valores and linea == f"{nombre}=":
            linea = f"{nombre}={valores[nombre]}"
        for rol, variable in URLS.items():
            linea = linea.replace(f"{rol}:CAMBIAR@", f"{rol}:{valores[variable]}@")
        lineas.append(linea)
    resultado = "\n".join(lineas) + "\n"
    if "CAMBIAR@" in resultado or any(f"\n{n}=\n" in resultado for n in CONTRASENAS):
        raise SystemExit(
            "La plantilla .env.example cambió: no se pudieron completar las contraseñas"
        )
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--forzar", action="store_true", help="reemplazar un .env existente"
    )
    args = parser.parse_args()

    if DESTINO.exists() and not args.forzar:
        print(
            f"{DESTINO.name} ya existe; no se modifica (use --forzar para reemplazarlo)."
        )
        return 0
    contenido = generar(PLANTILLA.read_text(encoding="utf-8"))
    DESTINO.write_text(contenido, encoding="utf-8", newline="\n")
    print(
        f"{DESTINO.name} creado con contraseñas aleatorias para postgres, trulab_owner y trulab_app."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
