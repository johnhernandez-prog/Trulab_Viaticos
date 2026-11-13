"""API de `/catalogos` (S2-01, docs/api-design.md §5.3): proyectos, rubros, células.

Lectura de selectores: todos los roles (`catalogos:leer`). Administración (listar con uso, crear,
editar, activar/desactivar): solo SUPERADMIN (`catalogos:gestionar`).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.enums import Rol
from app.modules.catalogos.models import Celula, Proyecto, Rubro
from app.modules.usuarios.models import Usuario
from tests.fabricas import (
    bearer,
    crear_celula,
    crear_proyecto,
    crear_rubro,
    crear_usuario,
    crear_viatico,
)

URL = "/api/v1/catalogos"


def _actor(sesion: Session, rol: Rol = Rol.SUPERADMIN) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol)
    return usuario, bearer(sesion, usuario)


def _auditoria(sesion: Session, accion: str, entidad_id: uuid.UUID) -> list[Auditoria]:
    return list(
        sesion.scalars(
            select(Auditoria)
            .where(
                Auditoria.accion == accion,
                Auditoria.entidad_id == entidad_id,
                Auditoria.created_at >= func.now(),
            )
            .order_by(Auditoria.id)
        )
    )


# --- permisos -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "leer", "gestionar"),
    [
        (Rol.VIAJERO, 200, 403),
        (Rol.FINANCIERO, 200, 403),
        (Rol.ADMIN, 200, 403),
        (Rol.SUPERADMIN, 200, 201),
    ],
)
def test_permisos_por_rol(
    api: TestClient, sesion: Session, rol: Rol, leer: int, gestionar: int
) -> None:
    _, encabezados = _actor(sesion, rol)

    assert api.get(URL, headers=encabezados).status_code == leer
    nombre = f"Rubro {uuid.uuid4().hex[:8]}"
    respuesta = api.post(f"{URL}/rubros", json={"nombre": nombre}, headers=encabezados)
    assert respuesta.status_code == gestionar


def test_listar_admin_exige_superadmin(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.ADMIN)

    assert api.get(f"{URL}/rubros", headers=encabezados).status_code == 403


def test_sin_token(api: TestClient) -> None:
    assert api.get(URL).status_code == 401


# --- GET /catalogos (combinado, selectores) -----------------------------------------------------


def test_listar_combinado_solo_activos(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.VIAJERO)
    activo = crear_proyecto(sesion, nombre=f"Activo {uuid.uuid4().hex[:8]}")
    inactivo = crear_proyecto(sesion, nombre=f"Inactivo {uuid.uuid4().hex[:8]}", activo=False)
    crear_rubro(sesion)
    crear_celula(sesion)

    respuesta = api.get(URL, headers=encabezados)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    ids_proyecto = {p["id"] for p in cuerpo["proyectos"]}
    assert str(activo.id) in ids_proyecto
    assert str(inactivo.id) not in ids_proyecto
    assert len(cuerpo["rubros"]) >= 1
    assert len(cuerpo["celulas"]) >= 1
    assert "ciudades" in cuerpo


def test_listar_combinado_incluye_codigo_y_formato_prestador(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion, Rol.VIAJERO)
    proyecto = crear_proyecto(
        sesion,
        nombre=f"Conexión {uuid.uuid4().hex[:8]}",
        codigo="P-CONEXI-002",
        exige_formato_prestador=True,
    )

    cuerpo = api.get(URL, headers=encabezados).json()

    fila = next(p for p in cuerpo["proyectos"] if p["id"] == str(proyecto.id))
    assert fila["codigo"] == "P-CONEXI-002"
    assert fila["exige_formato_prestador"] is True


def test_ciudades_segun_tipo_de_vinculacion(api: TestClient, sesion: Session) -> None:
    from tests.fabricas import crear_tarifa

    _, encabezados_empleado = _actor(sesion, Rol.VIAJERO)
    usuario_prestador = crear_usuario(sesion, rol=Rol.VIAJERO, es_prestador_servicios=True)
    encabezados_prestador = bearer(sesion, usuario_prestador)
    ciudad = f"Ciudad {uuid.uuid4().hex[:8]}"
    crear_tarifa(sesion, ciudad=ciudad, es_prestador_servicios=False)
    crear_tarifa(sesion, ciudad=f"{ciudad} prestador", es_prestador_servicios=True)

    cuerpo_empleado = api.get(URL, headers=encabezados_empleado).json()
    cuerpo_prestador = api.get(URL, headers=encabezados_prestador).json()

    assert ciudad in cuerpo_empleado["ciudades"]
    assert f"{ciudad} prestador" not in cuerpo_empleado["ciudades"]
    assert f"{ciudad} prestador" in cuerpo_prestador["ciudades"]
    assert ciudad not in cuerpo_prestador["ciudades"]


# --- GET /catalogos/{tipo} (admin, con uso) -------------------------------------------------------


def _crear_del_tipo(sesion: Session, tipo: str) -> Proyecto | Rubro | Celula:
    if tipo == "proyectos":
        return crear_proyecto(sesion)
    if tipo == "rubros":
        return crear_rubro(sesion)
    return crear_celula(sesion)


@pytest.mark.parametrize("tipo", ["proyectos", "rubros", "celulas"])
def test_listar_admin_incluye_inactivos_y_uso(api: TestClient, sesion: Session, tipo: str) -> None:
    _, encabezados = _actor(sesion)
    inactivo = _crear_del_tipo(sesion, tipo)
    inactivo.activo = False
    sesion.flush()

    respuesta = api.get(f"{URL}/{tipo}", headers=encabezados)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    fila = next(f for f in cuerpo if f["id"] == str(inactivo.id))
    assert fila["activo"] is False
    assert fila["uso"] == 0


def test_listar_admin_tipo_invalido(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    assert api.get(f"{URL}/no-existe", headers=encabezados).status_code == 422


def test_uso_de_proyecto_cuenta_viaticos_y_gastos(api: TestClient, sesion: Session) -> None:
    from app.core.enums import Modalidad
    from tests.fabricas import crear_gasto

    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)
    crear_viatico(
        sesion, modalidad=Modalidad.CON_SOLICITUD, proyecto_id=proyecto.id, proyecto_otro=None
    )
    viatico_directo = crear_viatico(sesion, modalidad=Modalidad.LEGALIZACION_DIRECTA)
    crear_gasto(sesion, viatico_directo, proyecto_id=proyecto.id, proyecto_otro=None)

    cuerpo = api.get(f"{URL}/proyectos", headers=encabezados).json()

    fila = next(f for f in cuerpo if f["id"] == str(proyecto.id))
    assert fila["uso"] == 2


def test_uso_de_celula_cuenta_usuarios_activos_e_inactivos(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion)
    celula = crear_celula(sesion)
    crear_usuario(sesion, celula_id=celula.id, activo=False)

    cuerpo = api.get(f"{URL}/celulas", headers=encabezados).json()

    fila = next(f for f in cuerpo if f["id"] == str(celula.id))
    assert fila["uso"] == 1


# --- crear ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", ["proyectos", "rubros", "celulas"])
def test_crear(api: TestClient, sesion: Session, tipo: str) -> None:
    actor, encabezados = _actor(sesion)
    nombre = f"Nuevo {tipo} {uuid.uuid4().hex[:8]}"

    respuesta = api.post(f"{URL}/{tipo}", json={"nombre": nombre, "orden": 3}, headers=encabezados)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == nombre
    assert respuesta.headers["location"] == f"{URL}/{tipo}/{cuerpo['id']}"
    modelo = {"proyectos": Proyecto, "rubros": Rubro, "celulas": Celula}[tipo]
    fila = sesion.get(modelo, uuid.UUID(cuerpo["id"]))
    assert fila is not None and fila.created_by == actor.id and fila.orden == 3
    (evento,) = _auditoria(sesion, "CATALOGO_CREAR", fila.id)
    assert evento.datos["tipo"] == tipo


def test_crear_proyecto_con_codigo_y_formato_prestador(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        f"{URL}/proyectos",
        json={
            "nombre": f"Conexión {uuid.uuid4().hex[:8]}",
            "codigo": "P-CONEXI-900",
            "exige_formato_prestador": True,
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "P-CONEXI-900"
    assert cuerpo["exige_formato_prestador"] is True


@pytest.mark.parametrize("tipo", ["rubros", "celulas"])
def test_codigo_no_aplica_fuera_de_proyectos(api: TestClient, sesion: Session, tipo: str) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        f"{URL}/{tipo}",
        json={"nombre": f"X {uuid.uuid4().hex[:8]}", "codigo": "ALGO"},
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


def _crear_con_nombre(sesion: Session, tipo: str, nombre: str) -> Proyecto | Rubro | Celula:
    if tipo == "proyectos":
        return crear_proyecto(sesion, nombre=nombre)
    if tipo == "rubros":
        return crear_rubro(sesion, nombre)
    return crear_celula(sesion, nombre)


@pytest.mark.parametrize("tipo", ["proyectos", "rubros", "celulas"])
def test_nombre_duplicado_sin_distinguir_mayusculas(
    api: TestClient, sesion: Session, tipo: str
) -> None:
    _, encabezados = _actor(sesion)
    nombre = f"Duplicado {uuid.uuid4().hex[:8]}"
    _crear_con_nombre(sesion, tipo, nombre)

    respuesta = api.post(f"{URL}/{tipo}", json={"nombre": nombre.upper()}, headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "DUPLICADO"


def test_codigo_de_proyecto_duplicado(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    crear_proyecto(sesion, codigo="P-DUP-001")

    respuesta = api.post(
        f"{URL}/proyectos",
        json={"nombre": f"Otro {uuid.uuid4().hex[:8]}", "codigo": "p-dup-001"},
        headers=encabezados,
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "DUPLICADO"


@pytest.mark.parametrize("cuerpo", [{"nombre": "   "}, {}])
def test_crear_rechaza_datos_invalidos(
    api: TestClient, sesion: Session, cuerpo: dict[str, str]
) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(f"{URL}/rubros", json=cuerpo, headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


# --- editar ---------------------------------------------------------------------------------


def test_editar_nombre_y_orden(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    rubro = crear_rubro(sesion, "Viáticos")

    respuesta = api.patch(
        f"{URL}/rubros/{rubro.id}",
        json={"nombre": "Viáticos de campo", "orden": 1},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Viáticos de campo"
    sesion.refresh(rubro)
    assert rubro.updated_by == actor.id and rubro.orden == 1
    (evento,) = _auditoria(sesion, "CATALOGO_EDITAR", rubro.id)
    assert evento.datos["despues"]["nombre"] == "Viáticos de campo"


def test_editar_proyecto_codigo_y_formato_prestador(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.patch(
        f"{URL}/proyectos/{proyecto.id}",
        json={"codigo": "P-NUEVO-001", "exige_formato_prestador": True},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "P-NUEVO-001"
    assert cuerpo["exige_formato_prestador"] is True


def test_editar_a_nombre_existente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    crear_rubro(sesion, "Transporte")
    rubro = crear_rubro(sesion, "Hospedaje")

    respuesta = api.patch(
        f"{URL}/rubros/{rubro.id}", json={"nombre": "transporte"}, headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "DUPLICADO"


def test_editar_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.patch(f"{URL}/rubros/{uuid.uuid4()}", json={"nombre": "X"}, headers=encabezados)

    assert respuesta.status_code == 404


# --- activar / desactivar ----------------------------------------------------------------------


def test_desactivar_y_activar(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    celula = crear_celula(sesion)

    respuesta = api.post(f"{URL}/celulas/{celula.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == str(celula.id)
    sesion.refresh(celula)
    assert celula.activo is False and celula.updated_by == actor.id
    assert len(_auditoria(sesion, "CATALOGO_DESACTIVAR", celula.id)) == 1

    respuesta = api.post(f"{URL}/celulas/{celula.id}/activar", headers=encabezados)

    assert respuesta.status_code == 200
    sesion.refresh(celula)
    assert celula.activo is True
    assert len(_auditoria(sesion, "CATALOGO_ACTIVAR", celula.id)) == 1


def test_desactivar_es_idempotente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    celula = crear_celula(sesion)
    celula.activo = False
    sesion.flush()

    respuesta = api.post(f"{URL}/celulas/{celula.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200
    assert len(_auditoria(sesion, "CATALOGO_DESACTIVAR", celula.id)) == 0


def test_desactivar_no_impide_valores_en_uso(api: TestClient, sesion: Session) -> None:
    # RN-24: se desactiva igual; solo se evita que vuelva a aparecer en los selectores.
    _, encabezados = _actor(sesion)
    celula = crear_celula(sesion)
    crear_usuario(sesion, celula_id=celula.id)

    respuesta = api.post(f"{URL}/celulas/{celula.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200
