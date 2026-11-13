"""Rutas de `/archivos` y `/me/firma` (docs/api-design.md §5.1 y §5.9; S2-06).

- `POST /archivos` (multipart): sube un archivo con su `proposito`; el tipo real se valida por
  contenido (RN-13). Después se adjunta por su `id` (gastos, firma). Un `Content-Length`
  excesivo lo corta antes `LimiteCuerpoAdjuntosMiddleware` (app/core/middleware.py); aquí el
  contenido se lee con límite.
- `GET /archivos/{id}/url`: URL temporal de lectura (S3 prefirmada o firmada en local), con el
  alcance de RLS (quien lo subió, o FINANCIERO/ADMIN/SUPERADMIN).
- `GET /archivos/contenido?token=`: solo con `STORAGE_BACKEND=local`; sirve el contenido a quien
  tenga un token vigente (el equivalente local de la URL prefirmada de S3).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from app.core.config import get_settings
from app.core.enums import PropositoArchivo
from app.core.errors import NoEncontrado
from app.core.permissions import Permiso, require_permission
from app.modules.archivos import service
from app.modules.archivos.errores import ArchivoMuyGrande
from app.modules.archivos.schemas import ArchivoSalida, ArchivoUrl, FirmaAsignar, FirmaSalida
from app.modules.archivos.storage import (
    Almacenamiento,
    AlmacenamientoLocal,
    TokenArchivoInvalidoError,
    content_disposition,
    get_almacenamiento,
)
from app.modules.auth.dependencias import DB, Autenticado, Config, UsuarioActual

router = APIRouter(prefix="/archivos", tags=["archivos"])
router_firma = APIRouter(prefix="/me/firma", tags=["archivos"])

Almacen = Annotated[Almacenamiento, Depends(get_almacenamiento)]
Subidor = Annotated[Autenticado, Depends(require_permission(Permiso.GASTOS_GESTIONAR_PROPIOS))]
Lector = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_LEER_PROPIOS))]

_BLOQUE = 1024 * 1024


def _limite_bytes() -> int:
    return get_settings().max_upload_mb * 1024 * 1024


def _leer_con_limite(archivo: UploadFile, limite: int) -> bytes:
    partes: list[bytes] = []
    leidos = 0
    while bloque := archivo.file.read(_BLOQUE):
        leidos += len(bloque)
        if leidos > limite:
            raise ArchivoMuyGrande(detail=f"Máximo {limite // (1024 * 1024)} MB por archivo")
        partes.append(bloque)
    return b"".join(partes)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Subir un archivo (tipo validado por contenido; RN-13)",
)
def subir(
    autenticado: Subidor,
    session: DB,
    almacenamiento: Almacen,
    response: Response,
    archivo: Annotated[UploadFile, File(description="Contenido del archivo (máx. 10 MB)")],
    proposito: Annotated[PropositoArchivo, Form()],
) -> ArchivoSalida:
    contenido = _leer_con_limite(archivo, _limite_bytes())
    registro = service.subir(
        session,
        almacenamiento,
        autenticado.usuario,
        proposito=proposito,
        nombre=archivo.filename,
        contenido=contenido,
    )
    response.headers["Location"] = f"/api/v1/archivos/{registro.id}"
    return ArchivoSalida.model_validate(registro)


@router.get(
    "/contenido",
    summary="Contenido de un archivo con un token temporal (solo STORAGE_BACKEND=local)",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def contenido(token: str, almacenamiento: Almacen) -> Response:
    if not isinstance(almacenamiento, AlmacenamientoLocal):
        raise NoEncontrado()
    try:
        datos = almacenamiento.verificar_token(token)
        cuerpo = almacenamiento.leer(str(datos["k"]))
    except (TokenArchivoInvalidoError, OSError, ValueError) as error:
        raise NoEncontrado() from error
    return Response(
        content=cuerpo,
        media_type=str(datos["m"]),
        headers={
            "Content-Disposition": content_disposition(str(datos["n"])),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/{archivo_id}", summary="Metadatos de un archivo (quien lo subió, F A S)")
def detalle(archivo_id: uuid.UUID, _: Lector, session: DB) -> ArchivoSalida:
    return ArchivoSalida.model_validate(service.obtener(session, archivo_id))


@router.get(
    "/{archivo_id}/url",
    summary="URL temporal de lectura de un archivo (5 min; quien lo subió, F A S)",
)
def url(
    archivo_id: uuid.UUID, _: Lector, session: DB, almacenamiento: Almacen, settings: Config
) -> ArchivoUrl:
    archivo = service.obtener(session, archivo_id)
    return service.url_lectura(almacenamiento, archivo, settings.signed_url_ttl_seconds)


# --- /me/firma (RN-32) --------------------------------------------------------------------------


@router_firma.put("", summary="Guardar la firma del perfil (archivo subido con propósito FIRMA)")
def asignar_firma(
    datos: FirmaAsignar,
    autenticado: UsuarioActual,
    session: DB,
    almacenamiento: Almacen,
    settings: Config,
) -> FirmaSalida:
    return service.asignar_firma(
        session,
        almacenamiento,
        autenticado.usuario,
        datos.archivo_id,
        settings.signed_url_ttl_seconds,
    )


@router_firma.get("", summary="Firma del perfil (URL temporal); 404 si no tiene")
def obtener_firma(
    autenticado: UsuarioActual, session: DB, almacenamiento: Almacen, settings: Config
) -> FirmaSalida:
    return service.obtener_firma(
        session, almacenamiento, autenticado.usuario, settings.signed_url_ttl_seconds
    )


@router_firma.delete(
    "", status_code=status.HTTP_204_NO_CONTENT, summary="Quitar la firma del perfil"
)
def quitar_firma(autenticado: UsuarioActual, session: DB) -> None:
    service.quitar_firma(session, autenticado.usuario)
