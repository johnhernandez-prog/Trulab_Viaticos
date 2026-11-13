/**
 * "Olvidé mi contraseña" (F-01c paso 1). La respuesta es la misma exista o no la cuenta: la
 * pantalla nunca revela si el usuario existe.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Mail } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Campo } from "@/components/ui/campo";
import { AuthLayout, EnlaceVolver } from "@/features/auth/AuthLayout";
import { esquemaOlvide, type DatosOlvide } from "@/features/auth/esquemas";
import { api } from "@/lib/api-client";
import { mensajeDeError } from "@/lib/errores";

export function OlvidePasswordPage() {
  const [enviado, setEnviado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<DatosOlvide>({ resolver: zodResolver(esquemaOlvide) });

  const enviar = handleSubmit(async (datos) => {
    setError(null);
    try {
      await api.post("/auth/password/forgot", datos);
      setEnviado(true);
    } catch (causa) {
      setError(mensajeDeError(causa));
    }
  });

  return (
    <AuthLayout
      titulo="Recuperar contraseña"
      descripcion="Le enviaremos un enlace para crear una contraseña nueva."
    >
      {enviado ? (
        <Alert variant="success" titulo="Revise su correo">
          Si la cuenta existe y está activa, enviaremos un enlace al correo registrado. El enlace
          vence pronto y solo sirve una vez.
        </Alert>
      ) : (
        <form onSubmit={(e) => void enviar(e)} noValidate className="space-y-4">
          <Campo
            etiqueta="Usuario o correo"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            ayuda="Los superadministradores gestionan su acceso en Google Workspace."
            error={errors.identificador?.message}
            {...register("identificador")}
          />
          {error && <Alert variant="destructive">{error}</Alert>}
          <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <Mail aria-hidden="true" />
            )}
            {isSubmitting ? "Enviando…" : "Enviar enlace"}
          </Button>
        </form>
      )}
      <EnlaceVolver />
    </AuthLayout>
  );
}
