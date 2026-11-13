/**
 * BottomBar del móvil (docs/design-system.md §12): 64 px, hasta 4 destinos; si el rol tiene más,
 * los 3 primeros y "Más", que abre un panel inferior con el resto.
 */
import { Ellipsis, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router";

import { repartirBarraInferior, type Modulo } from "@/components/layout/navegacion";
import { cn } from "@/lib/utils";

const destino =
  "flex min-h-14 flex-1 flex-col items-center justify-center gap-1 rounded-md px-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function BarraInferior({ modulos }: { modulos: Modulo[] }) {
  const { barra, mas } = repartirBarraInferior(modulos);
  const { pathname } = useLocation();
  // "Más" recuerda en qué ruta se abrió: al navegar a un módulo queda cerrado solo.
  const [abiertoEn, setAbiertoEn] = useState<string | null>(null);
  const masAbierto = abiertoEn === pathname;
  const setMasAbierto = (valor: boolean) => setAbiertoEn(valor ? pathname : null);
  const botonMas = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const enMas = mas.some((m) => pathname.startsWith(m.ruta));

  useEffect(() => {
    if (!masAbierto) return;
    panel.current?.querySelector<HTMLElement>("a")?.focus();
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAbiertoEn(null);
        botonMas.current?.focus();
      }
    };
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, [masAbierto]);

  return (
    <>
      {masAbierto && (
        <div className="fixed inset-0 z-40 sm:hidden">
          <div
            className="absolute inset-0 bg-foreground/30"
            onClick={() => setMasAbierto(false)}
            aria-hidden="true"
          />
          <div
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-label="Más secciones"
            className="absolute inset-x-0 bottom-0 rounded-t-xl border-t bg-card p-4 pb-[calc(5rem+env(safe-area-inset-bottom))] shadow-lg"
          >
            <div className="mb-3 flex items-center justify-between">
              <p className="text-lg font-semibold">Más</p>
              <button
                type="button"
                onClick={() => setMasAbierto(false)}
                aria-label="Cerrar"
                className="flex size-11 items-center justify-center rounded-md text-muted-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>
            <ul className="grid grid-cols-2 gap-2">
              {mas.map(({ ruta, etiqueta, icono: Icono, descripcion }) => (
                <li key={ruta}>
                  <NavLink
                    to={ruta}
                    className={({ isActive }) =>
                      cn(
                        "flex h-full min-h-14 flex-col gap-1 rounded-lg border p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        isActive ? "border-primary bg-primary/5 text-primary" : "hover:bg-accent",
                      )
                    }
                  >
                    <Icono className="size-5" aria-hidden="true" />
                    <span className="text-sm font-medium">{etiqueta}</span>
                    <span className="line-clamp-2 text-xs text-muted-foreground">
                      {descripcion}
                    </span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <nav
        aria-label="Navegación inferior"
        className="fixed inset-x-0 bottom-0 z-50 border-t bg-card pb-[env(safe-area-inset-bottom)] sm:hidden"
      >
        <ul className="flex h-16 items-stretch gap-1 px-2 py-1">
          {barra.map(({ ruta, etiqueta, icono: Icono }) => (
            <li key={ruta} className="flex flex-1">
              <NavLink
                to={ruta}
                className={({ isActive }) =>
                  cn(destino, isActive ? "text-primary" : "text-muted-foreground")
                }
              >
                <Icono className="size-5" aria-hidden="true" />
                {etiqueta}
              </NavLink>
            </li>
          ))}
          {mas.length > 0 && (
            <li className="flex flex-1">
              <button
                ref={botonMas}
                type="button"
                onClick={() => setMasAbierto(!masAbierto)}
                aria-expanded={masAbierto}
                aria-haspopup="dialog"
                className={cn(
                  destino,
                  masAbierto || enMas ? "text-primary" : "text-muted-foreground",
                )}
              >
                <Ellipsis className="size-5" aria-hidden="true" />
                Más
              </button>
            </li>
          )}
        </ul>
      </nav>
    </>
  );
}
