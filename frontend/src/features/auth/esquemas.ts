/**
 * Validación en el cliente con las mismas reglas que la API (docs/design-system.md §6). La API
 * vuelve a validar; sus `errors[]` se muestran en el campo correspondiente.
 */
import { z } from "zod";

/** Política de contraseñas (RN-15): 12–128 caracteres. El resto lo verifica la API. */
export const PASSWORD_MINIMO = 12;
export const PASSWORD_MAXIMO = 128;
export const AYUDA_POLITICA = `Al menos ${PASSWORD_MINIMO} caracteres. No use su usuario, su correo ni contraseñas comunes.`;

const requerido = (mensaje: string) => z.string().trim().min(1, mensaje);

const passwordNueva = z
  .string()
  .min(PASSWORD_MINIMO, `Use al menos ${PASSWORD_MINIMO} caracteres`)
  .max(PASSWORD_MAXIMO, `Use como máximo ${PASSWORD_MAXIMO} caracteres`);

export const esquemaLogin = z.object({
  username: requerido("Escriba su usuario").max(254),
  password: z.string().min(1, "Escriba su contraseña").max(256),
});
export type DatosLogin = z.infer<typeof esquemaLogin>;

export const esquemaOlvide = z.object({
  identificador: requerido("Escriba su usuario o su correo").max(254),
});
export type DatosOlvide = z.infer<typeof esquemaOlvide>;

const conConfirmacion = <T extends z.ZodRawShape>(forma: T) =>
  z
    .object({ ...forma, nueva_password: passwordNueva, confirmacion: z.string() })
    .refine((d) => d.nueva_password === d.confirmacion, {
      message: "Las contraseñas no coinciden",
      path: ["confirmacion"],
    });

export const esquemaRestablecer = conConfirmacion({});
export type DatosRestablecer = z.infer<typeof esquemaRestablecer>;

export const esquemaCambiar = conConfirmacion({
  password_actual: z.string().min(1, "Escriba su contraseña actual").max(256),
}).refine((d) => d.password_actual !== d.nueva_password, {
  message: "La contraseña nueva debe ser distinta de la actual",
  path: ["nueva_password"],
});
export type DatosCambiar = z.infer<typeof esquemaCambiar>;

export const esquemaDesarrollo = z.object({
  correo: requerido("Escriba el correo del superadministrador").email("Correo no válido"),
});
export type DatosDesarrollo = z.infer<typeof esquemaDesarrollo>;
