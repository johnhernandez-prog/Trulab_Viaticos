/**
 * Contexto de autenticación y hooks de lectura (`useAuth`, `usePermisos`).
 *
 * Los permisos en el frontend son solo para la experiencia (ocultar menú y rutas); la
 * autorización real está en el backend (docs/architecture.md §2).
 */
import { createContext, useContext } from "react";

import type { components } from "@/types/api";

export type UsuarioActual = components["schemas"]["UsuarioActualSalida"];
export type Permiso = components["schemas"]["Permiso"];
export type Rol = components["schemas"]["Rol"];

export type EstadoAuth =
  | { estado: "cargando" }
  | { estado: "anonimo"; motivo?: "sesion_perdida" | "sin_conexion" }
  | { estado: "autenticado"; usuario: UsuarioActual };

export interface AuthContexto {
  auth: EstadoAuth;
  iniciarSesion: (username: string, password: string) => Promise<UsuarioActual>;
  iniciarSesionGoogle: (idToken: string) => Promise<UsuarioActual>;
  /** Solo con `ENV=local` en la API (`/auth/dev/login`). */
  iniciarSesionDesarrollo: (correo: string) => Promise<UsuarioActual>;
  cambiarPassword: (actual: string, nueva: string) => Promise<UsuarioActual>;
  cerrarSesion: () => Promise<void>;
}

export const ContextoAuth = createContext<AuthContexto | null>(null);

export function useAuth(): AuthContexto {
  const contexto = useContext(ContextoAuth);
  if (!contexto) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return contexto;
}

/** Usuario autenticado; solo dentro de rutas protegidas por `RequiereSesion`. */
export function useUsuario(): UsuarioActual {
  const { auth } = useAuth();
  if (auth.estado !== "autenticado") throw new Error("useUsuario requiere una sesión activa");
  return auth.usuario;
}

export function usePermisos() {
  const { auth } = useAuth();
  const permisos = auth.estado === "autenticado" ? auth.usuario.permisos : [];
  return {
    permisos,
    tiene: (permiso: Permiso) => permisos.includes(permiso),
  };
}
