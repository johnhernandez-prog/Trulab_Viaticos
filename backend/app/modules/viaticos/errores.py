"""Errores de viáticos con su `code` estable (docs/api-design.md §5.4 y §7)."""

from app.core.errors import ErrorDominio


class TrayectosInvalidos(ErrorDominio):
    # RN-30: 1 a 5 trayectos, destino distinto del origen (salvo "Otro"), regreso >= ida.
    status = 422
    code = "TRAYECTOS_INVALIDOS"
    title = "Los trayectos de la solicitud no son válidos"


class ProyectoRequerido(ErrorDominio):
    # RN-16, ADR-031: ninguno de `proyecto_id`/`proyecto_otro`.
    status = 422
    code = "PROYECTO_REQUERIDO"
    title = 'Debe indicar un proyecto del catálogo o escribir uno con "Otro"'


class ProyectoAmbiguo(ErrorDominio):
    # RN-16, ADR-031: los dos a la vez.
    status = 422
    code = "PROYECTO_AMBIGUO"
    title = 'Indique un solo proyecto: del catálogo o escrito con "Otro"'


class FechaNacimientoRequerida(ErrorDominio):
    # RN-31: obligatoria en el perfil si `requiere_tiquete`.
    status = 422
    code = "FECHA_NACIMIENTO_REQUERIDA"
    title = "Se necesita la fecha de nacimiento para emitir el tiquete"
