/**
 * Login dual (F-01, ADR-027): usuario y contraseña para VIAJERO/ADMIN/FINANCIERO y Google
 * `@trulab.co` para SUPERADMIN. En desarrollo (`import.meta.env.DEV`), además, el acceso de
 * SUPERADMIN por correo contra `/auth/dev/login` (la API solo lo expone con `ENV=local`).
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, LogIn } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { AccesoDesarrollo } from "@/features/auth/AccesoDesarrollo";
import { AuthLayout } from "@/features/auth/AuthLayout";
import { BotonGoogle } from "@/features/auth/BotonGoogle";
import { useAuth, type UsuarioActual } from "@/features/auth/contexto";
import { esquemaLogin, type DatosLogin } from "@/features/auth/esquemas";
import { destinoTrasLogin, vistaInicial } from "@/features/auth/roles";
import { mensajeDeError } from "@/lib/errores";

export function LoginPage() {
  const { auth, iniciarSesion, iniciarSesionGoogle } = useAuth();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [conGoogle, setConGoogle] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<DatosLogin>({ resolver: zodResolver(esquemaLogin) });

  const entrar = (usuario: UsuarioActual) => {
    const { desde } = (ubicacion.state ?? {}) as { desde?: string };
    void navegar(destinoTrasLogin(desde, vistaInicial(usuario)), { replace: true });
  };

  const enviar = handleSubmit(async (datos) => {
    setError(null);
    try {
      entrar(await iniciarSesion(datos.username, datos.password));
    } catch (causa) {
      setError(mensajeDeError(causa));
    }
  });

  const entrarConGoogle = async (idToken: string) => {
    setError(null);
    setConGoogle(true);
    try {
      entrar(await iniciarSesionGoogle(idToken));
    } catch (causa) {
      setError(mensajeDeError(causa));
    } finally {
      setConGoogle(false);
    }
  };

  const ocupado = isSubmitting || conGoogle;

  return (
    <AuthLayout titulo="Iniciar sesión" descripcion="Ingrese con el usuario que le asignaron.">
      {auth.estado === "anonimo" && auth.motivo === "sesion_perdida" && (
        <Alert variant="warning">Su sesión terminó. Inicie sesión de nuevo.</Alert>
      )}
      {auth.estado === "anonimo" && auth.motivo === "sin_conexion" && (
        <Alert variant="warning">
          No se pudo conectar con el servidor. Revise su conexión antes de ingresar.
        </Alert>
      )}

      <form onSubmit={(e) => void enviar(e)} noValidate className="space-y-4">
        <Campo
          etiqueta="Usuario"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          error={errors.username?.message}
          {...register("username")}
        />
        <Campo
          etiqueta="Contraseña"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <div className="flex justify-end">
          <Link
            to="/olvide-password"
            className="rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Olvidé mi contraseña
          </Link>
        </div>

        {error && <Alert variant="destructive">{error}</Alert>}

        <Button type="submit" size="lg" className="w-full" disabled={ocupado}>
          {isSubmitting ? (
            <>
              <Loader2 className="animate-spin" aria-hidden="true" />
              Ingresando…
            </>
          ) : (
            <>
              <LogIn aria-hidden="true" />
              Ingresar
            </>
          )}
        </Button>
      </form>

      <section aria-labelledby="titulo-superadmin" className="space-y-3">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span className="h-px flex-1 bg-border" aria-hidden="true" />
          <h2 id="titulo-superadmin" className="font-medium">
            Superadministradores de Trulab
          </h2>
          <span className="h-px flex-1 bg-border" aria-hidden="true" />
        </div>
        <BotonGoogle alObtenerToken={(t) => void entrarConGoogle(t)} deshabilitado={ocupado} />
        {import.meta.env.DEV && <AccesoDesarrollo alEntrar={entrar} alError={setError} />}
      </section>
    </AuthLayout>
  );
}
