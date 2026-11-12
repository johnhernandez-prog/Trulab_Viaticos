import type { RouteObject } from "react-router";

import { ErrorRuta } from "@/app/ErrorRuta";
import { NoEncontradoPage } from "@/app/NoEncontradoPage";
import { AppShell } from "@/components/layout/AppShell";
import { InicioPage } from "@/features/inicio/InicioPage";

/**
 * Tabla de rutas de la SPA. Cada feature agrega aquí sus rutas (lista, detalle...).
 * Las guardas de autenticación y de rol llegan con S1-11.
 */
export const rutas: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    errorElement: <ErrorRuta />,
    children: [
      { index: true, element: <InicioPage /> },
      { path: "*", element: <NoEncontradoPage /> },
    ],
  },
];
