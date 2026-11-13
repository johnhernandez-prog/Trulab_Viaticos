"""RLS sobre `viaticos`, `viatico_trayectos`, `viatico_eventos`, `gastos` y `archivos` (S2-03,
docs/database-design.md §6, ADR-007).

Todo corre como `trulab_app` (la conexión de la API, sin `BYPASSRLS`): el fixture `sesion` fija un
contexto privilegiado por defecto (SUPERADMIN) para que las fábricas puedan insertar; cada prueba
de aislamiento lo cambia con `fijar_contexto_rls()` antes de consultar o escribir, exactamente como
lo hace `_autenticado()` en cada petición real.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.db import fijar_contexto_rls
from app.core.enums import AccionViatico, Etapa, Modalidad, Rol
from app.modules.archivos.models import Archivo
from app.modules.auth.dependencias import DB, Autenticado, UsuarioActual
from app.modules.gastos.models import Gasto
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico, ViaticoEvento, ViaticoTrayecto
from tests.fabricas import bearer, crear_archivo, crear_gasto, crear_usuario, crear_viatico

V, F, A, S = Rol.VIAJERO, Rol.FINANCIERO, Rol.ADMIN, Rol.SUPERADMIN


def _como(sesion: Session, usuario: Usuario) -> None:
    fijar_contexto_rls(sesion, usuario.id, usuario.rol)


def _trayecto(sesion: Session, viatico: Viatico) -> ViaticoTrayecto:
    ida = datetime(2026, 11, 20, 8, tzinfo=UTC)
    trayecto = ViaticoTrayecto(
        viatico_id=viatico.id,
        orden=1,
        ciudad_origen="Cali",
        ciudad_destino="Bogotá",
        fecha_ida=ida,
        fecha_regreso=ida + timedelta(days=2),
        dias_estadia=3,
    )
    sesion.add(trayecto)
    sesion.flush()
    return trayecto


def _evento(sesion: Session, viatico: Viatico) -> ViaticoEvento:
    evento = ViaticoEvento(
        viatico_id=viatico.id,
        etapa=Etapa.LEGALIZACION,
        accion=AccionViatico.CREAR,
        usuario_id=viatico.usuario_id,
    )
    sesion.add(evento)
    sesion.flush()
    return evento


# --- viaticos: visibilidad propia o privilegiada --------------------------------------------------


def test_viajero_solo_ve_sus_propios_viaticos(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)
    viatico_a = crear_viatico(sesion, usuario=viajero_a)
    crear_viatico(sesion, usuario=viajero_b)

    _como(sesion, viajero_a)
    visibles = sesion.scalars(select(Viatico)).all()

    assert [v.id for v in visibles] == [viatico_a.id]


@pytest.mark.parametrize("rol", [F, A, S])
def test_roles_privilegiados_ven_todos_los_viaticos(sesion: Session, rol: Rol) -> None:
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=V))
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=V))
    privilegiado = crear_usuario(sesion, rol=rol)

    _como(sesion, privilegiado)
    visibles = sesion.scalars(select(Viatico)).all()

    assert len(visibles) >= 2


def test_sin_contexto_no_se_ve_ningun_viatico(sesion: Session) -> None:
    crear_viatico(sesion)
    fijar_contexto_rls(sesion, uuid.uuid4(), V)  # usuario que no es dueño de nada
    sesion.flush()

    assert sesion.scalars(select(Viatico)).all() == []


def test_viajero_no_puede_crear_un_viatico_a_nombre_de_otro(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)

    _como(sesion, viajero_a)
    with pytest.raises(ProgrammingError, match="row-level security"):
        crear_viatico(sesion, usuario=viajero_b)


def test_viajero_si_puede_crear_su_propio_viatico(sesion: Session) -> None:
    viajero = crear_usuario(sesion, rol=V)

    _como(sesion, viajero)
    viatico = crear_viatico(sesion, usuario=viajero)

    assert viatico.usuario_id == viajero.id


def test_admin_puede_crear_un_viatico_a_nombre_de_otro(sesion: Session) -> None:
    # Distinto de RN-27 (sin autoaprobación): RLS solo protege la visibilidad y la pertenencia de
    # la fila; los permisos y RN-27 los aplica el service (docs/database-design.md §6, nota final).
    admin = crear_usuario(sesion, rol=A)
    viajero = crear_usuario(sesion, rol=V)

    _como(sesion, admin)
    viatico = crear_viatico(sesion, usuario=viajero)

    assert viatico.usuario_id == viajero.id


# --- viatico_trayectos y viatico_eventos: siguen al viático padre ---------------------------------


def test_trayectos_siguen_la_visibilidad_del_viatico(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)
    viatico_a = crear_viatico(sesion, usuario=viajero_a, modalidad=Modalidad.CON_SOLICITUD)
    viatico_b = crear_viatico(sesion, usuario=viajero_b, modalidad=Modalidad.CON_SOLICITUD)
    trayecto_a = _trayecto(sesion, viatico_a)
    _trayecto(sesion, viatico_b)

    _como(sesion, viajero_a)
    visibles = sesion.scalars(select(ViaticoTrayecto)).all()

    assert [t.id for t in visibles] == [trayecto_a.id]


def test_eventos_siguen_la_visibilidad_del_viatico(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)
    viatico_a = crear_viatico(sesion, usuario=viajero_a)
    viatico_b = crear_viatico(sesion, usuario=viajero_b)
    evento_a = _evento(sesion, viatico_a)
    _evento(sesion, viatico_b)

    _como(sesion, viajero_a)
    visibles = sesion.scalars(select(ViaticoEvento)).all()

    assert [e.id for e in visibles] == [evento_a.id]


def test_financiero_ve_eventos_de_cualquier_viatico(sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    evento = _evento(sesion, viatico)
    financiero = crear_usuario(sesion, rol=F)

    _como(sesion, financiero)
    visibles = sesion.scalars(select(ViaticoEvento)).all()

    assert evento.id in {e.id for e in visibles}


def test_no_se_puede_registrar_un_evento_de_un_viatico_ajeno(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viatico_de_otro = crear_viatico(sesion, usuario=crear_usuario(sesion, rol=V))

    _como(sesion, viajero_a)
    with pytest.raises(ProgrammingError, match="row-level security"):
        _evento(sesion, viatico_de_otro)


# --- gastos: siguen al viático padre --------------------------------------------------------------


def test_gastos_siguen_la_visibilidad_del_viatico(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)
    viatico_a = crear_viatico(sesion, usuario=viajero_a)
    viatico_b = crear_viatico(sesion, usuario=viajero_b)
    gasto_a = crear_gasto(sesion, viatico_a)
    crear_gasto(sesion, viatico_b)

    _como(sesion, viajero_a)
    visibles = sesion.scalars(select(Gasto)).all()

    assert [g.id for g in visibles] == [gasto_a.id]


def test_no_se_puede_registrar_un_gasto_en_un_viatico_ajeno(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viatico_de_otro = crear_viatico(sesion, usuario=crear_usuario(sesion, rol=V))

    _como(sesion, viajero_a)
    with pytest.raises(ProgrammingError, match="row-level security"):
        crear_gasto(sesion, viatico_de_otro)


# --- archivos: por quien lo subió (`created_by`) --------------------------------------------------


def test_viajero_solo_ve_los_archivos_que_subio(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)
    archivo_a = crear_archivo(sesion, created_by=viajero_a.id)
    crear_archivo(sesion, created_by=viajero_b.id)

    _como(sesion, viajero_a)
    visibles = sesion.scalars(select(Archivo)).all()

    assert [a.id for a in visibles] == [archivo_a.id]


@pytest.mark.parametrize("rol", [F, A, S])
def test_roles_privilegiados_ven_todos_los_archivos(sesion: Session, rol: Rol) -> None:
    crear_archivo(sesion, created_by=crear_usuario(sesion, rol=V).id)
    crear_archivo(sesion, created_by=crear_usuario(sesion, rol=V).id)
    privilegiado = crear_usuario(sesion, rol=rol)

    _como(sesion, privilegiado)
    visibles = sesion.scalars(select(Archivo)).all()

    assert len(visibles) >= 2


def test_no_se_puede_registrar_un_archivo_a_nombre_de_otro(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)

    _como(sesion, viajero_a)
    with pytest.raises(ProgrammingError, match="row-level security"):
        crear_archivo(sesion, created_by=viajero_b.id)


# --- consulta SQL directa (sin ORM), para confirmar que no depende de cómo arma la consulta -------


def test_aislamiento_tambien_con_sql_directo(sesion: Session) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viatico_a = crear_viatico(sesion, usuario=viajero_a)
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=V))

    _como(sesion, viajero_a)
    filas = sesion.execute(text("SELECT id FROM viaticos")).scalars().all()

    assert filas == [viatico_a.id]


# --- de punta a punta por HTTP: el contexto lo fija la autenticación real -------------------------


@pytest.fixture
def api_viaticos(app: FastAPI, api: TestClient) -> TestClient:
    """Ruta de prueba que hace exactamente lo que hará `GET /viaticos` (S2-05): un `SELECT` sin
    filtrar por dueño, confiando en que RLS (y no el código de la ruta) hace el recorte (RN-01,
    ADR-007). Reemplaza el `GET /viaticos` real, que todavía no existe (llega en S2-05)."""

    router = APIRouter(prefix="/api/v1/_prueba_rls")

    @router.get("/viaticos")
    def listar(autenticado: UsuarioActual, session: DB) -> list[str]:
        assert isinstance(autenticado, Autenticado)
        return [str(v.id) for v in session.scalars(select(Viatico)).all()]

    app.include_router(router)
    return api


def test_http_un_viajero_solo_ve_sus_propios_viaticos(
    api_viaticos: TestClient, sesion: Session
) -> None:
    viajero_a = crear_usuario(sesion, rol=V)
    viajero_b = crear_usuario(sesion, rol=V)
    viatico_a = crear_viatico(sesion, usuario=viajero_a)
    crear_viatico(sesion, usuario=viajero_b)

    respuesta = api_viaticos.get("/api/v1/_prueba_rls/viaticos", headers=bearer(sesion, viajero_a))

    assert respuesta.status_code == 200
    assert respuesta.json() == [str(viatico_a.id)]


def test_http_financiero_ve_todos_los_viaticos(api_viaticos: TestClient, sesion: Session) -> None:
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=V))
    crear_viatico(sesion, usuario=crear_usuario(sesion, rol=V))
    financiero = crear_usuario(sesion, rol=F)

    respuesta = api_viaticos.get("/api/v1/_prueba_rls/viaticos", headers=bearer(sesion, financiero))

    assert respuesta.status_code == 200
    assert len(respuesta.json()) >= 2
