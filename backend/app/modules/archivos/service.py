"""Reglas de archivos (S2-06; RN-13, RN-32, ADR-028).

- **Subir:** el tipo se detecta por contenido (`deteccion.py`), nunca por extensión ni por el
  `Content-Type` del cliente; debe corresponder al propósito. Se calcula el SHA-256, se guarda el
  contenido (inmutable) y después la fila de `archivos`, ligada al usuario autenticado
  (`created_by`). Si la BD falla, el objeto queda huérfano en el almacenamiento (la purga de
  huérfanos es una tarea futura); nunca al revés (fila sin contenido).
- **Leer:** el alcance lo aplica RLS (`archivos`: quien lo subió, o FINANCIERO/ADMIN/SUPERADMIN);
  sin fila visible → `404`. Se entrega una URL temporal, no el contenido.
- **Adjuntar** (gastos, firma): el archivo debe existir, ser de quien adjunta y tener el
  propósito esperado (`validar_adjunto`).
"""

import hashlib
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import PropositoArchivo
from app.core.errors import NoEncontrado, ValorNoPermitido, error_de_campo
from app.modules.archivos import deteccion
from app.modules.archivos.errores import TipoArchivoNoPermitido
from app.modules.archivos.models import Archivo
from app.modules.archivos.schemas import ArchivoUrl, FirmaSalida
from app.modules.archivos.storage import Almacenamiento
from app.modules.usuarios.models import Usuario

_NOMBRE_MAXIMO = 255


def sanear_nombre(nombre: str | None, mime_type: str) -> str:
    """Solo el nombre (sin ruta), sin caracteres de control, recortado; con respaldo si queda
    vacío. Es solo informativo: la clave de almacenamiento nunca usa el nombre del cliente."""
    base = (nombre or "").replace("\\", "/").rsplit("/", 1)[-1]
    limpio = "".join(c for c in base if unicodedata.category(c)[0] != "C").strip()
    if not limpio:
        limpio = f"archivo{deteccion.EXTENSION[mime_type]}"
    return limpio[:_NOMBRE_MAXIMO]


def subir(
    session: Session,
    almacenamiento: Almacenamiento,
    actor: Usuario,
    *,
    proposito: PropositoArchivo,
    nombre: str | None,
    contenido: bytes,
) -> Archivo:
    if not contenido:
        raise ValorNoPermitido(errors=error_de_campo("archivo", "El archivo está vacío"))
    mime_type = deteccion.detectar_mime(contenido)
    if mime_type is None or not deteccion.permitido(proposito, mime_type):
        permitidos = ", ".join(sorted(deteccion.PERMITIDOS[proposito]))
        raise TipoArchivoNoPermitido(
            detail=f"Para {proposito.value} solo se admiten: {permitidos}",
            errors=error_de_campo(
                "archivo", "El contenido no corresponde a un tipo permitido", "TIPO_NO_PERMITIDO"
            ),
        )

    ahora = datetime.now(UTC)
    clave = (
        f"{proposito.value.lower()}/{ahora:%Y/%m}/{uuid.uuid4()}{deteccion.EXTENSION[mime_type]}"
    )
    almacenamiento.guardar(clave, contenido, mime_type)

    archivo = Archivo(
        created_by=actor.id,
        storage_key=clave,
        nombre_original=sanear_nombre(nombre, mime_type),
        mime_type=mime_type,
        tamano_bytes=len(contenido),
        sha256=hashlib.sha256(contenido).hexdigest(),
        proposito=proposito,
    )
    session.add(archivo)
    session.commit()
    session.refresh(archivo)
    return archivo


def obtener(session: Session, archivo_id: uuid.UUID) -> Archivo:
    """Sin filtrar por dueño a propósito: RLS ya oculta lo ajeno a un VIAJERO (→ `404`)."""
    archivo = session.scalar(select(Archivo).where(Archivo.id == archivo_id))
    if archivo is None:
        raise NoEncontrado()
    return archivo


def url_lectura(almacenamiento: Almacenamiento, archivo: Archivo, ttl_segundos: int) -> ArchivoUrl:
    expira = datetime.now(UTC) + timedelta(seconds=ttl_segundos)
    url = almacenamiento.url_lectura(
        archivo.storage_key,
        mime_type=archivo.mime_type,
        nombre=archivo.nombre_original,
        expira_en=ttl_segundos,
    )
    return ArchivoUrl(
        url=url, expires_at=expira, mime_type=archivo.mime_type, nombre=archivo.nombre_original
    )


def validar_adjunto(
    session: Session,
    archivo_id: uuid.UUID,
    actor: Usuario,
    proposito: PropositoArchivo,
    campo: str,
) -> Archivo:
    """El archivo existe, lo subió `actor` y tiene el propósito (y el tipo) que pide `campo`."""
    archivo = session.scalar(select(Archivo).where(Archivo.id == archivo_id))
    if archivo is None or archivo.created_by != actor.id:
        # Ajeno o inexistente: el mismo mensaje (no se revela que existe).
        raise ValorNoPermitido(errors=error_de_campo(campo, "El archivo no existe"))
    if archivo.proposito != proposito or not deteccion.permitido(proposito, archivo.mime_type):
        raise TipoArchivoNoPermitido(
            detail=f"'{campo}' exige un archivo subido con propósito {proposito.value}",
            errors=error_de_campo(campo, "Tipo de archivo no permitido", "TIPO_NO_PERMITIDO"),
        )
    return archivo


# --- firma del perfil (RN-32) -------------------------------------------------------------------


def _firma_salida(
    almacenamiento: Almacenamiento, archivo: Archivo, ttl_segundos: int
) -> FirmaSalida:
    url = url_lectura(almacenamiento, archivo, ttl_segundos)
    return FirmaSalida(archivo_id=archivo.id, **url.model_dump())


def asignar_firma(
    session: Session,
    almacenamiento: Almacenamiento,
    actor: Usuario,
    archivo_id: uuid.UUID,
    ttl_segundos: int,
) -> FirmaSalida:
    archivo = validar_adjunto(session, archivo_id, actor, PropositoArchivo.FIRMA, "archivo_id")
    actor.firma_archivo_id = archivo.id
    session.commit()
    return _firma_salida(almacenamiento, archivo, ttl_segundos)


def obtener_firma(
    session: Session, almacenamiento: Almacenamiento, actor: Usuario, ttl_segundos: int
) -> FirmaSalida:
    if actor.firma_archivo_id is None:
        raise NoEncontrado(detail="No tiene una firma guardada en el perfil")
    return _firma_salida(almacenamiento, obtener(session, actor.firma_archivo_id), ttl_segundos)


def quitar_firma(session: Session, actor: Usuario) -> None:
    # El archivo no se borra (inmutable): las solicitudes que ya lo usan lo conservan.
    actor.firma_archivo_id = None
    session.commit()
