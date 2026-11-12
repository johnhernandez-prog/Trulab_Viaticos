import { CircleAlert, CircleCheck, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSaludApi } from "@/features/inicio/useSaludApi";

/**
 * Tarjeta temporal que comprueba la comunicación SPA → API (`GET /api/v1/health`).
 * Implementa los estados de interfaz del design system (§11): cargando, error con
 * "Reintentar" y datos; el estado siempre lleva texto, nunca solo color.
 */
export function EstadoApi() {
  const { data, isPending, isError, refetch, isFetching } = useSaludApi();

  return (
    <section
      aria-labelledby="estado-api"
      className="rounded-lg border bg-card p-4 shadow-sm sm:p-6"
    >
      <h2 id="estado-api" className="text-lg font-semibold">
        Estado de la API
      </h2>

      {isPending && (
        <div className="mt-4 space-y-2" aria-busy="true" aria-label="Consultando la API">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-5 w-32" />
        </div>
      )}

      {isError && (
        <div className="mt-4 space-y-3" role="alert">
          <p className="flex items-center gap-2 text-destructive">
            <CircleAlert className="size-4" aria-hidden="true" />
            No se pudo conectar con la API.
          </p>
          <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
            <RefreshCw aria-hidden="true" />
            Reintentar
          </Button>
        </div>
      )}

      {data && (
        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">API</dt>
          <dd>{data.status === "ok" ? "Disponible" : "Con problemas"}</dd>
          <dt className="text-muted-foreground">Base de datos</dt>
          <dd className="flex items-center gap-1.5">
            {data.db === "ok" ? (
              <>
                <CircleCheck className="size-4 text-success" aria-hidden="true" />
                Conectada
              </>
            ) : (
              <>
                <CircleAlert className="size-4 text-destructive" aria-hidden="true" />
                Sin conexión
              </>
            )}
          </dd>
          <dt className="text-muted-foreground">Versión</dt>
          <dd className="tabular-nums">{data.version}</dd>
        </dl>
      )}
    </section>
  );
}
