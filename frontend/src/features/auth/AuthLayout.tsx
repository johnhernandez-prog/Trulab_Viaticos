import { ArrowLeft, Plane } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

/**
 * Marco de las pantallas sin sesión (login, recuperación y cambio de contraseña).
 * Móvil: una columna con la marca arriba. Escritorio: panel de marca a la izquierda.
 */
export function AuthLayout({
  titulo,
  descripcion,
  children,
}: {
  titulo: string;
  descripcion?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh bg-background">
      <aside className="relative hidden w-[44%] max-w-xl flex-col justify-between overflow-hidden bg-primary p-10 text-primary-foreground lg:flex">
        <Marca invertida />
        <div className="space-y-4">
          <p className="text-3xl font-semibold leading-tight">
            Viáticos claros, de la solicitud a la legalización.
          </p>
          <p className="max-w-sm text-primary-foreground/80">
            Solicite, cargue sus facturas desde el celular y consulte su saldo en un solo lugar.
          </p>
        </div>
        <p className="text-sm text-primary-foreground/70">Trulab · Uso interno</p>
        {/* Decoración: no transmite información. */}
        <Plane
          className="pointer-events-none absolute -right-10 top-1/3 size-72 -rotate-12 text-primary-foreground/10"
          aria-hidden="true"
        />
      </aside>

      <main className="flex flex-1 flex-col items-center justify-center px-4 py-10 sm:px-6">
        <div className="w-full max-w-sm space-y-6">
          <div className="lg:hidden">
            <Marca />
          </div>
          <div className="space-y-1.5">
            <h1 className="text-xl font-semibold sm:text-2xl">{titulo}</h1>
            {descripcion && <div className="text-muted-foreground">{descripcion}</div>}
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

function Marca({ invertida = false }: { invertida?: boolean }) {
  return (
    <p className="flex items-center gap-2 text-lg font-semibold">
      <span
        className={
          invertida
            ? "flex size-9 items-center justify-center rounded-lg bg-primary-foreground/15"
            : "flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground"
        }
      >
        <Plane className="size-5" aria-hidden="true" />
      </span>
      Trulab Viajes
    </p>
  );
}

export function EnlaceVolver() {
  return (
    <Link
      to="/login"
      className="inline-flex min-h-11 items-center gap-2 rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-0"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      Volver a iniciar sesión
    </Link>
  );
}
