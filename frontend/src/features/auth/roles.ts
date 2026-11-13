import type { Rol, UsuarioActual } from "@/features/auth/contexto";

export const ETIQUETA_ROL: Record<Rol, string> = {
  VIAJERO: "Viajero",
  FINANCIERO: "Financiero",
  ADMIN: "Administrador",
  SUPERADMIN: "Superadministrador",
};

/** Vista inicial por rol (docs/user-flows.md F-01 y F-11). */
export function vistaInicial(usuario: Pick<UsuarioActual, "rol">): string {
  switch (usuario.rol) {
    case "ADMIN":
      return "/revision";
    case "FINANCIERO":
      return "/pagos";
    default:
      return "/viaticos";
  }
}

export function iniciales(nombre: string): string {
  const partes = nombre.trim().split(/\s+/).filter(Boolean);
  const letras = partes.length > 1 ? [partes[0], partes[partes.length - 1]] : partes;
  return letras.map((p) => p?.[0]?.toUpperCase() ?? "").join("") || "?";
}

/** Solo rutas internas: un `desde` externo (`//otro.sitio`) no se sigue (open redirect). */
export function destinoTrasLogin(desde: string | undefined, porDefecto: string): string {
  if (!desde || !desde.startsWith("/") || desde.startsWith("//")) return porDefecto;
  if (desde === "/login" || desde === "/") return porDefecto;
  return desde;
}
