/**
 * Marcador de los módulos que llegan en las semanas siguientes (viáticos, pagos, indicadores...).
 * Permite navegar el AppShell y probar las guardas por permiso antes de tener las pantallas.
 */
import { Construction } from "lucide-react";

import type { Modulo } from "@/components/layout/navegacion";

export function ModuloPendientePage({ modulo }: { modulo: Modulo }) {
  const Icono = modulo.icono;
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Icono className="size-6 text-primary" aria-hidden="true" />
        <h1 className="text-xl font-semibold sm:text-2xl">{modulo.etiqueta}</h1>
      </div>
      <section className="flex flex-col items-center gap-3 rounded-lg border border-dashed bg-card px-4 py-12 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-muted">
          <Construction className="size-6 text-muted-foreground" aria-hidden="true" />
        </div>
        <p className="font-medium">Este módulo está en construcción</p>
        <p className="max-w-md text-sm text-muted-foreground">{modulo.descripcion}</p>
      </section>
    </div>
  );
}
