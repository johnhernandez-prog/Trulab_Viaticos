/**
 * Mensajes en lenguaje claro según el `code` estable de la API (docs/api-design.md §7).
 * La UI nunca muestra el texto técnico del servidor.
 */
import { ApiError, SIN_CONEXION } from "@/lib/api-client";

const MENSAJES: Record<string, string> = {
  [SIN_CONEXION]: "No se pudo conectar con el servidor. Revise su conexión e intente de nuevo.",
  CREDENCIALES_INVALIDAS: "Usuario o contraseña incorrectos.",
  CUENTA_BLOQUEADA_TEMPORALMENTE:
    "Cuenta bloqueada temporalmente por intentos fallidos. Intente en 15 minutos.",
  DEMASIADAS_SOLICITUDES: "Demasiados intentos seguidos. Espere un momento e intente de nuevo.",
  DOMINIO_NO_PERMITIDO: "Use su cuenta corporativa @trulab.co.",
  USUARIO_NO_REGISTRADO: "Su cuenta no tiene acceso. Contacte al administrador.",
  USUARIO_INACTIVO: "Su cuenta no tiene acceso. Contacte al administrador.",
  METODO_ACCESO_NO_PERMITIDO:
    "Este acceso no corresponde a su cuenta. Use su usuario y contraseña.",
  LOGIN_GOOGLE_NO_DISPONIBLE: "El ingreso con Google no está configurado todavía.",
  PASSWORD_ACTUAL_INCORRECTA: "La contraseña actual no es correcta.",
  PASSWORD_DEBIL: "La contraseña nueva no cumple la política.",
  TOKEN_INVALIDO: "El enlace no es válido o venció. Solicite uno nuevo.",
  NO_AUTENTICADO: "Su sesión terminó. Inicie sesión de nuevo.",
  TOKEN_EXPIRADO: "Su sesión terminó. Inicie sesión de nuevo.",
  SIN_PERMISO: "No tiene permiso para realizar esta acción.",
  CAMBIO_PASSWORD_REQUERIDO: "Debe cambiar su contraseña temporal antes de continuar.",
  ERROR_INTERNO: "Ocurrió un error en el servidor. Intente de nuevo en unos minutos.",
};

const GENERICO = "Ocurrió un error inesperado. Intente de nuevo.";

export function mensajeDeError(error: unknown): string {
  if (error instanceof ApiError) return MENSAJES[error.code] ?? GENERICO;
  return GENERICO;
}

/** Mensajes de `errors[]` de un campo (por ejemplo, las reglas de la política de contraseñas). */
export function erroresDeCampo(error: unknown, campo: string): string[] {
  if (!(error instanceof ApiError)) return [];
  return error.errors.filter((e) => e.field === campo).map((e) => e.message);
}
