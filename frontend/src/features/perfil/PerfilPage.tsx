/**
 * Perfil del usuario autenticado (F-11). La firma y la fecha de nacimiento editables llegan con
 * `/me/firma` y `PATCH /me` (semana 2).
 */
import { KeyRound, LogOut } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useAuth, useUsuario } from "@/features/auth/contexto";
import { ETIQUETA_ROL, iniciales } from "@/features/auth/roles";

export function PerfilPage() {
  const usuario = useUsuario();
  const { cerrarSesion } = useAuth();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const [saliendo, setSaliendo] = useState(false);
  const mensaje = (ubicacion.state as { mensaje?: string } | null)?.mensaje;

  const datos: [string, string][] = [
    ["Rol", ETIQUETA_ROL[usuario.rol]],
    ["Usuario", usuario.username ?? "Ingresa con Google"],
    ["Correo", usuario.correo],
    ["Cargo", usuario.cargo?.nombre ?? "Sin asignar"],
    ["Célula", usuario.celula?.nombre ?? "Sin asignar"],
    ["Vinculación", usuario.es_prestador_servicios ? "Prestador de servicios" : "Empleado"],
  ];

  const salir = async () => {
    setSaliendo(true);
    await cerrarSesion();
    void navegar("/login", { replace: true });
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold sm:text-2xl">Mi perfil</h1>
      {mensaje && <Alert variant="success">{mensaje}</Alert>}

      <section className="rounded-lg border bg-card p-4 shadow-sm sm:p-6">
        <div className="flex items-center gap-4">
          <span
            className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary/10 text-lg font-semibold text-primary"
            aria-hidden="true"
          >
            {iniciales(usuario.nombre_completo)}
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{usuario.nombre_completo}</h2>
            <p className="truncate text-sm text-muted-foreground">{usuario.correo}</p>
          </div>
        </div>
        <dl className="mt-6 grid gap-x-6 gap-y-4 sm:grid-cols-2">
          {datos.map(([etiqueta, valor]) => (
            <div key={etiqueta} className="min-w-0">
              <dt className="text-sm text-muted-foreground">{etiqueta}</dt>
              <dd className="truncate font-medium">{valor}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="flex flex-col gap-3 sm:flex-row">
        {usuario.rol !== "SUPERADMIN" && (
          <Button asChild variant="secondary">
            <Link to="/cambiar-password">
              <KeyRound aria-hidden="true" />
              Cambiar contraseña
            </Link>
          </Button>
        )}
        <Button variant="outline" onClick={() => void salir()} disabled={saliendo}>
          <LogOut aria-hidden="true" />
          {saliendo ? "Cerrando sesión…" : "Cerrar sesión"}
        </Button>
      </div>
    </div>
  );
}
