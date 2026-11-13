import type { RouteObject } from "react-router";

import { ErrorRuta } from "@/app/ErrorRuta";
import { NoEncontradoPage } from "@/app/NoEncontradoPage";
import { AppShell } from "@/components/layout/AppShell";
import { MODULOS } from "@/components/layout/navegacion";
import { CambiarPasswordPage } from "@/features/auth/CambiarPasswordPage";
import {
  RequierePermiso,
  RequiereSesion,
  RUTA_CAMBIO_PASSWORD,
  SoloAnonimo,
  VistaInicial,
} from "@/features/auth/guardas";
import { LoginPage } from "@/features/auth/LoginPage";
import { OlvidePasswordPage } from "@/features/auth/OlvidePasswordPage";
import { RestablecerPasswordPage } from "@/features/auth/RestablecerPasswordPage";
import { ModuloPendientePage } from "@/features/modulos/ModuloPendientePage";
import { PerfilPage } from "@/features/perfil/PerfilPage";

/**
 * Tabla de rutas de la SPA (S1-11).
 *
 * - Públicas: recuperación y restablecimiento de contraseña (el enlace del correo debe abrir
 *   aunque haya otra sesión en el navegador).
 * - Solo sin sesión: `/login`.
 * - Con sesión: `/cambiar-password` (fuera del layout, también en el cambio obligatorio) y el
 *   AppShell. Cada módulo exige su permiso con `RequierePermiso`.
 *
 * Cada feature reemplaza su `ModuloPendientePage` cuando llega (semana 2 en adelante).
 */
export const rutas: RouteObject[] = [
  {
    errorElement: <ErrorRuta />,
    children: [
      { path: "/olvide-password", element: <OlvidePasswordPage /> },
      { path: "/restablecer-password", element: <RestablecerPasswordPage /> },
      { element: <SoloAnonimo />, children: [{ path: "/login", element: <LoginPage /> }] },
      {
        element: <RequiereSesion />,
        children: [
          { path: RUTA_CAMBIO_PASSWORD, element: <CambiarPasswordPage /> },
          {
            path: "/",
            element: <AppShell />,
            children: [
              { index: true, element: <VistaInicial /> },
              ...MODULOS.map((modulo) => ({
                path: modulo.ruta.slice(1),
                element: modulo.permiso ? (
                  <RequierePermiso permiso={modulo.permiso}>
                    <ModuloPendientePage modulo={modulo} />
                  </RequierePermiso>
                ) : (
                  <ModuloPendientePage modulo={modulo} />
                ),
              })),
              { path: "perfil", element: <PerfilPage /> },
              { path: "*", element: <NoEncontradoPage /> },
            ],
          },
        ],
      },
    ],
  },
];
