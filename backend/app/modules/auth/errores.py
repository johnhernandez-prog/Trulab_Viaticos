"""Errores de autenticación con su `code` estable (docs/api-design.md §3 y §7)."""

from app.core.errors import ErrorDominio


class CredencialesInvalidas(ErrorDominio):
    # Mismo mensaje para usuario inexistente, contraseña incorrecta, inactivo o SUPERADMIN:
    # no se revela cuál falló (el motivo real va solo a `auditoria`).
    status = 401
    code = "CREDENCIALES_INVALIDAS"
    title = "Usuario o contraseña incorrectos"


class NoAutenticado(ErrorDominio):
    status = 401
    code = "NO_AUTENTICADO"
    title = "Debe iniciar sesión"


class TokenExpirado(ErrorDominio):
    status = 401
    code = "TOKEN_EXPIRADO"
    title = "La sesión expiró"


class CuentaBloqueada(ErrorDominio):
    status = 429
    code = "CUENTA_BLOQUEADA_TEMPORALMENTE"
    title = "Cuenta bloqueada temporalmente por intentos fallidos. Intente más tarde"


class AccesoDenegado(ErrorDominio):
    status = 403
    code = "USUARIO_NO_REGISTRADO"
    title = "Su cuenta no tiene acceso. Contacte al administrador"


class UsuarioInactivo(AccesoDenegado):
    code = "USUARIO_INACTIVO"


class DominioNoPermitido(AccesoDenegado):
    code = "DOMINIO_NO_PERMITIDO"
    title = "Use su cuenta corporativa de Trulab"


class MetodoAccesoNoPermitido(AccesoDenegado):
    code = "METODO_ACCESO_NO_PERMITIDO"
    title = "Este método de acceso no corresponde a su rol"


class CambioPasswordRequerido(ErrorDominio):
    status = 403
    code = "CAMBIO_PASSWORD_REQUERIDO"
    title = "Debe cambiar su contraseña temporal antes de continuar"


class SolicitudSpaRequerida(ErrorDominio):
    # Mitigación CSRF de /auth/refresh y /auth/logout, junto con SameSite=Strict.
    status = 403
    code = "SIN_PERMISO"
    title = "Falta el encabezado X-Requested-With de la aplicación"


class PasswordDebil(ErrorDominio):
    status = 422
    code = "PASSWORD_DEBIL"
    title = "La contraseña no cumple la política"


class PasswordActualIncorrecta(ErrorDominio):
    status = 422
    code = "PASSWORD_ACTUAL_INCORRECTA"
    title = "La contraseña actual no es correcta"


class TokenRecuperacionInvalido(ErrorDominio):
    # Mensaje único: inexistente, usado o vencido.
    status = 422
    code = "TOKEN_INVALIDO"
    title = "El enlace no es válido o venció. Solicite uno nuevo"


class LoginGoogleNoDisponible(ErrorDominio):
    status = 503
    code = "LOGIN_GOOGLE_NO_DISPONIBLE"
    title = "El inicio de sesión con Google no está configurado"
