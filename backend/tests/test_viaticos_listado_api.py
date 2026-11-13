"""`GET /viaticos` (S2-05, docs/api-design.md §5.4): listado paginado con filtros.

RLS (S2-03) ya limita lo que ve un VIAJERO; aquí se prueba el contrato HTTP (filtros, paginación,
orden y el resumen financiero/`acciones_permitidas` de cada fila).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import EstadoFinanciero, Modalidad, Rol
from app.modules.usuarios.models import Usuario
from tests.fabricas import bearer, crear_proyecto, crear_usuario, crear_viatico

URL = "/api/v1/viaticos"


def _actor(
    sesion: Session, rol: Rol = Rol.VIAJERO, **campos: object
) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol, **campos)
    return usuario, bearer(sesion, usuario)


@pytest.mark.parametrize("rol", list(Rol))
def test_permisos_listar(api: TestClient, sesion: Session, rol: Rol) -> None:
    _, encabezados = _actor(sesion, rol)

    respuesta = api.get(URL, headers=encabezados)

    assert respuesta.status_code == 200


def test_sin_token(api: TestClient) -> None:
    assert api.get(URL).status_code == 401


def test_viajero_solo_ve_sus_propios_viaticos(api: TestClient, sesion: Session) -> None:
    viajero_a, encabezados_a = _actor(sesion)
    viatico_a = crear_viatico(sesion, usuario=viajero_a)
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=Rol.VIAJERO))

    cuerpo = api.get(URL, headers=encabezados_a).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(viatico_a.id) in ids
    assert len(cuerpo["items"]) == 1


@pytest.mark.parametrize("rol", [Rol.FINANCIERO, Rol.ADMIN, Rol.SUPERADMIN])
def test_roles_privilegiados_ven_todos(api: TestClient, sesion: Session, rol: Rol) -> None:
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=Rol.VIAJERO))
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=Rol.VIAJERO))
    _, encabezados = _actor(sesion, rol)

    cuerpo = api.get(URL, headers=encabezados).json()

    assert cuerpo["total"] >= 2


def test_resumen_incluye_usuario_financiero_y_acciones(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)

    cuerpo = api.get(URL, headers=encabezados).json()

    fila = next(f for f in cuerpo["items"] if f["id"] == str(viatico.id))
    assert fila["usuario"] == {"id": str(viajero.id), "nombre": viajero.nombre_completo}
    assert fila["total_gastos"] == "0.00"
    assert fila["saldo"] == "0.00"
    assert "editar" in fila["acciones_permitidas"]
    assert "eliminar" in fila["acciones_permitidas"]


def test_orden_por_created_at_descendente(api: TestClient, sesion: Session) -> None:
    # `now()` en Postgres devuelve la hora de inicio de la transacción: dentro de la misma prueba
    # (una sola transacción) sería igual para ambos; se fija a mano para que el orden sea claro.
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    marca = uuid.uuid4().hex[:8]
    base = datetime(2026, 6, 1, tzinfo=UTC)
    primero = crear_viatico(sesion, motivo_viaje=f"Primero {marca}", created_at=base)
    segundo = crear_viatico(
        sesion, motivo_viaje=f"Segundo {marca}", created_at=base + timedelta(minutes=5)
    )

    cuerpo = api.get(URL, params={"q": marca}, headers=encabezados).json()

    ids = [f["id"] for f in cuerpo["items"]]
    assert ids.index(str(segundo.id)) < ids.index(str(primero.id))


def test_filtro_por_etapa_y_estado(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    directa = crear_viatico(sesion, modalidad=Modalidad.LEGALIZACION_DIRECTA)
    solicitud = crear_viatico(sesion, modalidad=Modalidad.CON_SOLICITUD)

    cuerpo = api.get(URL, params={"etapa": "SOLICITUD"}, headers=encabezados).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(solicitud.id) in ids
    assert str(directa.id) not in ids


def test_filtro_por_estado_financiero(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    transferido = crear_viatico(sesion, estado_financiero=EstadoFinanciero.TRANSFERIDO)
    pendiente = crear_viatico(sesion, estado_financiero=EstadoFinanciero.PENDIENTE)

    cuerpo = api.get(URL, params={"estado_financiero": "TRANSFERIDO"}, headers=encabezados).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(transferido.id) in ids
    assert str(pendiente.id) not in ids


def test_filtro_por_modalidad(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    directa = crear_viatico(sesion, modalidad=Modalidad.LEGALIZACION_DIRECTA)

    cuerpo = api.get(URL, params={"modalidad": "LEGALIZACION_DIRECTA"}, headers=encabezados).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(directa.id) in ids
    assert all(f["modalidad"] == "LEGALIZACION_DIRECTA" for f in cuerpo["items"])


def test_filtro_por_proyecto_id(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    proyecto = crear_proyecto(sesion)
    con_proyecto = crear_viatico(
        sesion, modalidad=Modalidad.CON_SOLICITUD, proyecto_id=proyecto.id, proyecto_otro=None
    )
    sin_proyecto = crear_viatico(sesion, modalidad=Modalidad.LEGALIZACION_DIRECTA)

    cuerpo = api.get(URL, params={"proyecto_id": str(proyecto.id)}, headers=encabezados).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(con_proyecto.id) in ids
    assert str(sin_proyecto.id) not in ids


def test_filtro_por_usuario_id(api: TestClient, sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico_a = crear_viatico(sesion, usuario=viajero_a)
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=Rol.VIAJERO))
    _, encabezados_admin = _actor(sesion, Rol.ADMIN)

    cuerpo = api.get(
        URL, params={"usuario_id": str(viajero_a.id)}, headers=encabezados_admin
    ).json()

    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["id"] == str(viatico_a.id)


def test_filtro_por_rango_de_fechas(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    dentro = crear_viatico(sesion, fecha_legalizacion=date(2026, 6, 15))
    fuera = crear_viatico(sesion, fecha_legalizacion=date(2026, 1, 1))

    cuerpo = api.get(
        URL,
        params={"desde": "2026-06-01", "hasta": "2026-06-30"},
        headers=encabezados,
    ).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(dentro.id) in ids
    assert str(fuera.id) not in ids


def test_busqueda_por_folio(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    viatico = crear_viatico(sesion)
    sesion.refresh(viatico)

    cuerpo = api.get(URL, params={"q": viatico.folio}, headers=encabezados).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(viatico.id) in ids


def test_busqueda_por_motivo(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    marca = uuid.uuid4().hex[:8]
    viatico = crear_viatico(sesion, motivo_viaje=f"Visita especial {marca}")

    cuerpo = api.get(URL, params={"q": marca}, headers=encabezados).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(viatico.id) in ids


def test_paginacion(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    marca = uuid.uuid4().hex[:8]
    for i in range(3):
        crear_viatico(sesion, motivo_viaje=f"Lote {marca} {i}")

    pagina1 = api.get(URL, params={"q": marca, "size": 2}, headers=encabezados).json()
    pagina2 = api.get(URL, params={"q": marca, "size": 2, "page": 2}, headers=encabezados).json()

    assert pagina1["total"] == 3 and pagina1["page"] == 1 and pagina1["size"] == 2
    assert len(pagina1["items"]) == 2
    assert len(pagina2["items"]) == 1


def test_viatico_eliminado_no_aparece(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    viatico.deleted_at = viatico.created_at
    sesion.flush()

    cuerpo = api.get(URL, headers=encabezados).json()

    ids = {f["id"] for f in cuerpo["items"]}
    assert str(viatico.id) not in ids
