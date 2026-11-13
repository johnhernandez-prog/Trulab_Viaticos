import { Plane } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";

/** Mientras se recupera la sesión: la forma del layout, sin spinner de página completa (§11). */
export function PantallaCarga() {
  return (
    <div className="flex min-h-dvh" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando la sesión…</span>
      <div className="hidden w-[72px] shrink-0 border-r bg-card p-3 sm:block lg:w-60">
        <div className="flex items-center gap-2 px-2 py-3">
          <Plane className="size-5 text-primary" aria-hidden="true" />
          <Skeleton className="hidden h-5 w-28 lg:block" />
        </div>
        <div className="mt-4 space-y-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      </div>
      <div className="flex-1 space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72 max-w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    </div>
  );
}
