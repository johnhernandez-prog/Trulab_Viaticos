/**
 * Layout de la app autenticada (docs/design-system.md §12):
 *
 * - **Móvil (< 640 px):** encabezado de 56 px con el menú de perfil y BottomBar de 64 px (hasta 4
 *   destinos, el resto en "Más"), respetando `safe-area-inset-bottom`.
 * - **Tablet (640–1023 px):** Sidebar plegable: riel de iconos de 72 px que se expande a 240 px
 *   como overlay.
 * - **Escritorio (≥ 1024 px):** Sidebar fija de 240 px y contenido con máximo de 1440 px.
 *
 * El menú se filtra con los permisos del usuario (`modulosVisibles`).
 */
import { Plane } from "lucide-react";
import { useCallback, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";

import { BarraInferior } from "@/components/layout/BarraInferior";
import { BarraLateral } from "@/components/layout/BarraLateral";
import { MenuPerfil } from "@/components/layout/MenuPerfil";
import { modulosVisibles } from "@/components/layout/navegacion";
import { usePermisos } from "@/features/auth/contexto";

export function AppShell() {
  const { tiene } = usePermisos();
  const modulos = modulosVisibles(tiene);
  const { pathname } = useLocation();
  // El overlay de la tablet recuerda en qué ruta se abrió: al navegar queda cerrado solo.
  const [expandidaEn, setExpandidaEn] = useState<string | null>(null);
  const lateralExpandida = expandidaEn === pathname;
  const setLateralExpandida = useCallback(
    (valor: boolean) => setExpandidaEn(valor ? pathname : null),
    [pathname],
  );

  return (
    <div className="flex min-h-dvh">
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-2 focus:z-[60] focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
      >
        Saltar al contenido
      </a>

      <BarraLateral
        modulos={modulos}
        expandida={lateralExpandida}
        alCambiarExpandida={setLateralExpandida}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Solo en móvil: en tablet y escritorio la marca y el perfil van en la Sidebar. */}
        <header className="sticky top-0 z-30 border-b bg-card sm:hidden">
          <div className="flex h-14 items-center justify-between gap-2 px-4">
            <Link
              to="/"
              className="flex min-h-11 items-center gap-2 rounded-md text-lg font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Plane className="size-5 text-primary" aria-hidden="true" />
              Trulab Viajes
            </Link>
            <MenuPerfil variante="encabezado" />
          </div>
        </header>

        <main
          id="contenido"
          tabIndex={-1}
          className="mx-auto w-full max-w-contenido flex-1 px-4 pb-[calc(5rem+env(safe-area-inset-bottom))] pt-6 focus:outline-none sm:px-6 sm:pb-8 lg:px-8"
        >
          <Outlet />
        </main>
      </div>

      <BarraInferior modulos={modulos} />
    </div>
  );
}
