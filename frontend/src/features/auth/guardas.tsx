/**
 * Guardas de ruta. Solo mejoran la experiencia: la API vuelve a validar sesión y permiso.
 *
 * - `RequiereSesion`: sin sesión → `/login` (recordando a dónde iba); con contraseña temporal →
 *   `/cambiar-password` antes de cualquier otra pantalla (F-01a paso 4).
 * - `SoloAnonimo`: el login no se muestra a quien ya tiene sesión.
 * - `RequierePermiso`: sin el permiso, la página "Sin acceso" dentro del layout.
 * - `VistaInicial`: `/` lleva a la vista inicial del rol.
 */
import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router";

import { SinAccesoPage } from "@/app/SinAccesoPage";
import { PantallaCarga } from "@/components/layout/PantallaCarga";
import { useAuth, usePermisos, type Permiso } from "@/features/auth/contexto";
import { destinoTrasLogin, vistaInicial } from "@/features/auth/roles";

export const RUTA_CAMBIO_PASSWORD = "/cambiar-password";

interface EstadoNavegacion {
  desde?: string;
}

export function RequiereSesion() {
  const { auth } = useAuth();
  const ubicacion = useLocation();

  if (auth.estado === "cargando") return <PantallaCarga />;
  if (auth.estado === "anonimo") {
    const desde = `${ubicacion.pathname}${ubicacion.search}`;
    return <Navigate to="/login" replace state={{ desde } satisfies EstadoNavegacion} />;
  }
  if (auth.usuario.debe_cambiar_password && ubicacion.pathname !== RUTA_CAMBIO_PASSWORD) {
    return <Navigate to={RUTA_CAMBIO_PASSWORD} replace />;
  }
  return <Outlet />;
}

export function SoloAnonimo() {
  const { auth } = useAuth();
  const ubicacion = useLocation();

  if (auth.estado === "cargando") return <PantallaCarga />;
  if (auth.estado === "autenticado") {
    const { desde } = (ubicacion.state ?? {}) as EstadoNavegacion;
    return <Navigate to={destinoTrasLogin(desde, vistaInicial(auth.usuario))} replace />;
  }
  return <Outlet />;
}

export function RequierePermiso({ permiso, children }: { permiso: Permiso; children: ReactNode }) {
  const { tiene } = usePermisos();
  return tiene(permiso) ? children : <SinAccesoPage />;
}

export function VistaInicial() {
  const { auth } = useAuth();
  if (auth.estado !== "autenticado") return null;
  return <Navigate to={vistaInicial(auth.usuario)} replace />;
}
