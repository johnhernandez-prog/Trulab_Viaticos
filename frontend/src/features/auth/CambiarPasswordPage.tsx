/**
 * Cambio de contraseña (F-01c paso 4): **obligatorio** si la contraseña es temporal (la API
 * rechaza el resto de endpoints hasta cambiarla) o voluntario desde el perfil.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound, Loader2, LogOut } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { AuthLayout } from "@/features/auth/AuthLayout";
import { useAuth, useUsuario } from "@/features/auth/contexto";
import { AYUDA_POLITICA, esquemaCambiar, type DatosCambiar } from "@/features/auth/esquemas";
import { vistaInicial } from "@/features/auth/roles";
import { erroresDeCampo, mensajeDeError } from "@/lib/errores";

export function CambiarPasswordPage() {
  const usuario = useUsuario();
  const { cambiarPassword, cerrarSesion } = useAuth();
  const navegar = useNavigate();
  const obligatorio = usuario.debe_cambiar_password;
  const [errorApi, setErrorApi] = useState<unknown>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<DatosCambiar>({ resolver: zodResolver(esquemaCambiar) });

  if (usuario.rol === "SUPERADMIN") {
    return (
      <AuthLayout titulo="Cambiar contraseña">
        <Alert variant="info">
          Los superadministradores entran con Google: su contraseña se gestiona en Google Workspace.
        </Alert>
        <Button asChild variant="secondary" className="w-full">
          <Link to="/perfil">Volver al perfil</Link>
        </Button>
      </AuthLayout>
    );
  }

  const enviar = handleSubmit(async ({ password_actual, nueva_password }) => {
    setErrorApi(null);
    try {
      const actualizado = await cambiarPassword(password_actual, nueva_password);
      void navegar(obligatorio ? vistaInicial(actualizado) : "/perfil", {
        replace: true,
        state: { mensaje: "Contraseña actualizada. Se cerraron sus otras sesiones." },
      });
    } catch (causa) {
      setErrorApi(causa);
    }
  });

  const delServidorActual = erroresDeCampo(errorApi, "password_actual");
  const delServidorNueva = erroresDeCampo(errorApi, "nueva_password");
  const mostrarGeneral =
    errorApi !== null && delServidorActual.length === 0 && delServidorNueva.length === 0;

  return (
    <AuthLayout
      titulo={obligatorio ? "Cree su contraseña" : "Cambiar contraseña"}
      descripcion={
        obligatorio
          ? `Hola, ${usuario.nombre_completo.split(" ")[0]}. Su contraseña es temporal: cámbiela para continuar.`
          : "Se cerrarán sus otras sesiones abiertas."
      }
    >
      <form onSubmit={(e) => void enviar(e)} noValidate className="space-y-4">
        <Campo
          etiqueta={obligatorio ? "Contraseña temporal" : "Contraseña actual"}
          type="password"
          autoComplete="current-password"
          error={[errors.password_actual?.message ?? "", ...delServidorActual]}
          {...register("password_actual")}
        />
        <Campo
          etiqueta="Contraseña nueva"
          type="password"
          autoComplete="new-password"
          ayuda={AYUDA_POLITICA}
          error={[errors.nueva_password?.message ?? "", ...delServidorNueva]}
          {...register("nueva_password")}
        />
        <Campo
          etiqueta="Confirme la contraseña nueva"
          type="password"
          autoComplete="new-password"
          error={errors.confirmacion?.message}
          {...register("confirmacion")}
        />
        {mostrarGeneral && <Alert variant="destructive">{mensajeDeError(errorApi)}</Alert>}
        <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : (
            <KeyRound aria-hidden="true" />
          )}
          {isSubmitting ? "Guardando…" : "Guardar contraseña"}
        </Button>
      </form>

      {obligatorio ? (
        <Button variant="ghost" className="w-full" onClick={() => void cerrarSesion()}>
          <LogOut aria-hidden="true" />
          Cerrar sesión
        </Button>
      ) : (
        <Button asChild variant="secondary" className="w-full">
          <Link to="/perfil">Cancelar</Link>
        </Button>
      )}
    </AuthLayout>
  );
}
