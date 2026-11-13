/**
 * "Nueva contraseña" desde el enlace del correo (F-01c paso 3): `/restablecer-password?token=…`.
 * El token se quita de la barra de direcciones al cargar (no queda en el historial ni se filtra
 * en el `Referer` de recursos externos).
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { AuthLayout, EnlaceVolver } from "@/features/auth/AuthLayout";
import {
  AYUDA_POLITICA,
  esquemaRestablecer,
  type DatosRestablecer,
} from "@/features/auth/esquemas";
import { api, ApiError } from "@/lib/api-client";
import { erroresDeCampo, mensajeDeError } from "@/lib/errores";

export function RestablecerPasswordPage() {
  const [parametros, setParametros] = useSearchParams();
  const [token] = useState(() => parametros.get("token") ?? "");
  const [listo, setListo] = useState(false);
  const [errorApi, setErrorApi] = useState<unknown>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<DatosRestablecer>({ resolver: zodResolver(esquemaRestablecer) });

  useEffect(() => {
    if (parametros.has("token")) setParametros({}, { replace: true });
  }, [parametros, setParametros]);

  const enviar = handleSubmit(async ({ nueva_password }) => {
    setErrorApi(null);
    try {
      await api.post("/auth/password/reset", { token, nueva_password });
      setListo(true);
    } catch (causa) {
      setErrorApi(causa);
    }
  });

  const tokenInvalido = errorApi instanceof ApiError && errorApi.code === "TOKEN_INVALIDO";

  let contenido;
  if (!token || tokenInvalido) {
    contenido = (
      <Alert variant="destructive" titulo="El enlace no es válido o venció">
        <p>
          Solicite uno nuevo desde{" "}
          <Link to="/olvide-password" className="font-medium text-primary underline">
            Olvidé mi contraseña
          </Link>
          .
        </p>
      </Alert>
    );
  } else if (listo) {
    contenido = (
      <div className="space-y-4">
        <Alert variant="success" titulo="Contraseña actualizada">
          Por seguridad se cerraron sus sesiones. Inicie sesión con la contraseña nueva.
        </Alert>
        <Button asChild size="lg" className="w-full">
          <Link to="/login">Iniciar sesión</Link>
        </Button>
      </div>
    );
  } else {
    const delServidor = erroresDeCampo(errorApi, "nueva_password");
    contenido = (
      <form onSubmit={(e) => void enviar(e)} noValidate className="space-y-4">
        <Campo
          etiqueta="Contraseña nueva"
          type="password"
          autoComplete="new-password"
          ayuda={AYUDA_POLITICA}
          error={[errors.nueva_password?.message ?? "", ...delServidor]}
          {...register("nueva_password")}
        />
        <Campo
          etiqueta="Confirme la contraseña nueva"
          type="password"
          autoComplete="new-password"
          error={errors.confirmacion?.message}
          {...register("confirmacion")}
        />
        {errorApi !== null && delServidor.length === 0 && (
          <Alert variant="destructive">{mensajeDeError(errorApi)}</Alert>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : (
            <KeyRound aria-hidden="true" />
          )}
          {isSubmitting ? "Guardando…" : "Guardar contraseña"}
        </Button>
      </form>
    );
  }

  return (
    <AuthLayout titulo="Nueva contraseña">
      {contenido}
      {!listo && <EnlaceVolver />}
    </AuthLayout>
  );
}
