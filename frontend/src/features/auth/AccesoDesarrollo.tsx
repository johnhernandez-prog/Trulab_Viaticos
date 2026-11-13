/**
 * Acceso de SUPERADMIN por correo, **solo en desarrollo** (R1.1: mientras no haya OAuth Client
 * ID). El bloque no se incluye en el build de producción (`import.meta.env.DEV`) y la API solo
 * expone `/auth/dev/login` con `ENV=local`.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { FlaskConical, Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { useAuth, type UsuarioActual } from "@/features/auth/contexto";
import { esquemaDesarrollo, type DatosDesarrollo } from "@/features/auth/esquemas";
import { mensajeDeError } from "@/lib/errores";

export function AccesoDesarrollo({
  alEntrar,
  alError,
}: {
  alEntrar: (usuario: UsuarioActual) => void;
  alError: (mensaje: string | null) => void;
}) {
  const { iniciarSesionDesarrollo } = useAuth();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<DatosDesarrollo>({ resolver: zodResolver(esquemaDesarrollo) });

  const enviar = handleSubmit(async ({ correo }) => {
    alError(null);
    try {
      alEntrar(await iniciarSesionDesarrollo(correo));
    } catch (causa) {
      alError(mensajeDeError(causa));
    }
  });

  return (
    <details className="group rounded-lg border border-dashed bg-card p-3 text-sm">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 font-medium text-muted-foreground sm:min-h-0">
        <FlaskConical className="size-4" aria-hidden="true" />
        Acceso de desarrollo (solo local)
      </summary>
      <form onSubmit={(e) => void enviar(e)} noValidate className="mt-3 space-y-3">
        <Campo
          etiqueta="Correo del superadministrador"
          type="email"
          autoComplete="email"
          placeholder="nombre@trulab.co"
          error={errors.correo?.message}
          {...register("correo")}
        />
        <Button type="submit" variant="secondary" className="w-full" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="animate-spin" aria-hidden="true" />}
          Entrar como superadministrador
        </Button>
      </form>
    </details>
  );
}
