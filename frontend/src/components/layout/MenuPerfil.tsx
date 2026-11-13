/**
 * Menú de perfil (F-01a "Cerrar sesión", F-01c "Cambiar contraseña"): iniciales del usuario y un
 * menú con Perfil, Cambiar contraseña (solo operativos) y Cerrar sesión.
 * Teclado: Enter/Espacio abre, flechas recorren, Esc cierra y devuelve el foco al botón.
 */
import { ChevronsUpDown, KeyRound, Loader2, LogOut, UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router";

import { useAuth, useUsuario } from "@/features/auth/contexto";
import { ETIQUETA_ROL, iniciales } from "@/features/auth/roles";
import { cn } from "@/lib/utils";

export function MenuPerfil({
  variante,
  expandida = false,
}: {
  variante: "encabezado" | "lateral";
  expandida?: boolean;
}) {
  const usuario = useUsuario();
  const { cerrarSesion } = useAuth();
  const navegar = useNavigate();
  const [abierto, setAbierto] = useState(false);
  const [saliendo, setSaliendo] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const idMenu = useId();

  useEffect(() => {
    if (!abierto) return;
    menu.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    const alPulsarFuera = (e: MouseEvent) => {
      if (!raiz.current?.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", alPulsarFuera);
    return () => document.removeEventListener("mousedown", alPulsarFuera);
  }, [abierto]);

  const cerrar = () => {
    setAbierto(false);
    boton.current?.focus();
  };

  const alTeclear = (e: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(menu.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    const actual = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      e.preventDefault();
      cerrar();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const paso = e.key === "ArrowDown" ? 1 : -1;
      items[(actual + paso + items.length) % items.length]?.focus();
    } else if (e.key === "Tab") {
      setAbierto(false);
    }
  };

  const salir = async () => {
    setSaliendo(true);
    await cerrarSesion();
    void navegar("/login", { replace: true });
  };

  const lateral = variante === "lateral";
  const textoVisible = cn(lateral && !expandida && "sm:sr-only lg:not-sr-only");
  const item =
    "flex min-h-11 w-full items-center gap-2 rounded-md px-3 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none sm:min-h-10";

  return (
    <div ref={raiz} className="relative" onKeyDown={alTeclear}>
      <button
        ref={boton}
        type="button"
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={abierto ? idMenu : undefined}
        aria-label={`Menú de ${usuario.nombre_completo}`}
        onClick={() => setAbierto((v) => !v)}
        className={cn(
          "flex min-h-11 items-center gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          lateral ? "w-full px-2 py-1.5 hover:bg-accent" : "justify-center",
        )}
      >
        <span
          className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary"
          aria-hidden="true"
        >
          {iniciales(usuario.nombre_completo)}
        </span>
        {lateral && (
          <>
            <span className={cn("min-w-0 flex-1", textoVisible)}>
              <span className="block truncate text-sm font-medium">{usuario.nombre_completo}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {ETIQUETA_ROL[usuario.rol]}
              </span>
            </span>
            <ChevronsUpDown
              className={cn("size-4 shrink-0 text-muted-foreground", textoVisible)}
              aria-hidden="true"
            />
          </>
        )}
      </button>

      {abierto && (
        <div
          ref={menu}
          id={idMenu}
          role="menu"
          aria-label="Opciones de la cuenta"
          className={cn(
            "absolute z-50 w-64 rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg",
            lateral ? "bottom-full left-0 mb-2" : "right-0 top-full mt-2",
          )}
        >
          <div className="border-b px-3 py-2">
            <p className="truncate text-sm font-medium">{usuario.nombre_completo}</p>
            <p className="truncate text-xs text-muted-foreground">
              {ETIQUETA_ROL[usuario.rol]} · {usuario.username ?? usuario.correo}
            </p>
          </div>
          <div className="pt-1">
            <Link to="/perfil" role="menuitem" className={item} onClick={() => setAbierto(false)}>
              <UserRound className="size-4" aria-hidden="true" />
              Mi perfil
            </Link>
            {usuario.rol !== "SUPERADMIN" && (
              <Link
                to="/cambiar-password"
                role="menuitem"
                className={item}
                onClick={() => setAbierto(false)}
              >
                <KeyRound className="size-4" aria-hidden="true" />
                Cambiar contraseña
              </Link>
            )}
            <button
              type="button"
              role="menuitem"
              className={cn(item, "text-destructive")}
              onClick={() => void salir()}
              disabled={saliendo}
            >
              {saliendo ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <LogOut className="size-4" aria-hidden="true" />
              )}
              Cerrar sesión
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
