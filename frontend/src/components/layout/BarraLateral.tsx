/**
 * Sidebar de tablet y escritorio. En tablet es un riel de 72 px con iconos (la etiqueta queda para
 * lectores de pantalla y en `title`) que se expande a 240 px como overlay; en escritorio siempre
 * mide 240 px.
 */
import { PanelLeftClose, PanelLeftOpen, Plane } from "lucide-react";
import { useEffect } from "react";
import { Link, NavLink } from "react-router";

import { MenuPerfil } from "@/components/layout/MenuPerfil";
import type { Modulo } from "@/components/layout/navegacion";
import { cn } from "@/lib/utils";

export function BarraLateral({
  modulos,
  expandida,
  alCambiarExpandida,
}: {
  modulos: Modulo[];
  expandida: boolean;
  alCambiarExpandida: (valor: boolean) => void;
}) {
  // Esc cierra el overlay de la tablet.
  useEffect(() => {
    if (!expandida) return;
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") alCambiarExpandida(false);
    };
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, [expandida, alCambiarExpandida]);

  // Texto que en el riel de la tablet solo leen los lectores de pantalla.
  const soloExpandida = cn(!expandida && "sm:sr-only lg:not-sr-only");

  return (
    <>
      {/* Reserva el ancho del riel: el overlay de la tablet no desplaza el contenido. */}
      <div className="hidden w-[72px] shrink-0 sm:block lg:w-60" aria-hidden="true" />

      {expandida && (
        <div
          className="fixed inset-0 z-40 hidden bg-foreground/30 sm:block lg:hidden"
          onClick={() => alCambiarExpandida(false)}
          aria-hidden="true"
        />
      )}

      <aside
        aria-label="Navegación principal"
        className={cn(
          "fixed inset-y-0 left-0 z-50 hidden flex-col border-r bg-card transition-[width] sm:flex lg:w-60 lg:shadow-none",
          expandida ? "w-60 shadow-lg" : "w-[72px]",
        )}
      >
        <div className="flex h-16 items-center border-b px-4">
          <Link
            to="/"
            className="flex min-h-11 items-center gap-2 rounded-md font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Plane className="size-5" aria-hidden="true" />
            </span>
            <span className={cn("truncate", soloExpandida)}>Trulab Viajes</span>
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto p-3" aria-label="Módulos">
          <ul className="space-y-1">
            {modulos.map(({ ruta, etiqueta, icono: Icono }) => (
              <li key={ruta}>
                <NavLink
                  to={ruta}
                  title={etiqueta}
                  className={({ isActive }) =>
                    cn(
                      "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isActive
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )
                  }
                >
                  <Icono className="size-5 shrink-0" aria-hidden="true" />
                  <span className={soloExpandida}>{etiqueta}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="space-y-1 border-t p-3">
          <button
            type="button"
            onClick={() => alCambiarExpandida(!expandida)}
            aria-expanded={expandida}
            aria-label={expandida ? "Contraer menú" : "Expandir menú"}
            className="flex min-h-11 w-full items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
          >
            {expandida ? (
              <PanelLeftClose className="size-5" aria-hidden="true" />
            ) : (
              <PanelLeftOpen className="size-5" aria-hidden="true" />
            )}
          </button>
          <MenuPerfil variante="lateral" expandida={expandida} />
        </div>
      </aside>
    </>
  );
}
