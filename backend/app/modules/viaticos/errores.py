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


class NoEditable(ErrorDominio):
    # RN-09/S-05: solo se edita o elimina con estado y estado_financiero PENDIENTE.
    status = 409
    code = "NO_EDITABLE"
    title = "El viático ya no se puede editar ni eliminar"


class ComentarioRequerido(ErrorDominio):
    # Rechazar y devolver exigen un comentario no vacío (RN-10).
    status = 422
    code = "COMENTARIO_REQUERIDO"
    title = "El comentario es obligatorio para esta acción"


class TransicionInvalida(ErrorDominio):
    # El estado operativo o financiero actual no admite esta transición.
    status = 409
    code = "TRANSICION_INVALIDA"
    title = "El viático no está en un estado que admita esta acción"


class AutoaprobacionNoPermitida(ErrorDominio):
    # RN-27: nadie aprueba, rechaza ni devuelve su propio viático, salvo SUPERADMIN (auditado).
    status = 403
    code = "AUTOAPROBACION_NO_PERMITIDA"
    title = "No puede aprobar, rechazar ni devolver su propio viático"


class ComprobanteFaltante(ErrorDominio):
    # RN-06/RN-21: para aprobar la legalización, al menos un gasto y todos con comprobante.
    status = 409
    code = "COMPROBANTE_FALTANTE"
    title = "Todos los gastos deben tener soporte o archivo para aprobar la legalización"


class LegalizacionNoHabilitable(ErrorDominio):
    # RN-28: condiciones para pasar de SOLICITUD aprobada a LEGALIZACION.
    status = 409
    code = "LEGALIZACION_NO_HABILITABLE"
    title = "La legalización no se puede habilitar todavía"
