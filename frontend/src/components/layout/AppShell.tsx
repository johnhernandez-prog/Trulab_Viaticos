import { Plane } from "lucide-react";
import { Link, Outlet } from "react-router";

/**
 * Layout raíz mínimo: encabezado de 56 px y contenido con los márgenes de página del design
 * system (`px-4` / `px-6` / `px-8`, máximo 1440 px).
 *
 * S1-11 lo reemplaza por el AppShell responsivo (BottomBar en móvil, Sidebar plegable en tablet
 * y fija en escritorio) con el menú según el rol (docs/design-system.md §12).
 */
export function AppShell() {
  return (
    <div className="flex min-h-dvh flex-col pb-[env(safe-area-inset-bottom)]">
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
      >
        Saltar al contenido
      </a>
      <header className="sticky top-0 z-40 border-b bg-card">
        <div className="mx-auto flex h-14 max-w-contenido items-center px-4 sm:px-6 lg:px-8">
          <Link
            to="/"
            className="flex items-center gap-2 rounded-md text-lg font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Plane className="size-5 text-primary" aria-hidden="true" />
            Trulab Viajes
          </Link>
        </div>
      </header>
      <main
        id="contenido"
        className="mx-auto w-full max-w-contenido flex-1 px-4 py-6 sm:px-6 lg:px-8"
      >
        <Outlet />
      </main>
    </div>
  );
}
