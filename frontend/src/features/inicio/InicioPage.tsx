import { EstadoApi } from "@/features/inicio/EstadoApi";

/**
 * Página principal TEMPORAL (S1-05). Se reemplaza cuando existan el login (S1-08, S1-11) y la
 * lista de legalizaciones (F4).
 */
export function InicioPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold sm:text-2xl">Trulab Viajes</h1>
        <p className="text-muted-foreground">
          Legalización de viáticos. Esta es una página temporal del esqueleto del frontend.
        </p>
      </div>
      <EstadoApi />
    </div>
  );
}
