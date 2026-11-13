/**
 * Botón "Ingresar con Google" (solo SUPERADMIN, F-01b) con Google Identity Services.
 *
 * El script de Google se carga **solo** si hay `VITE_GOOGLE_CLIENT_ID` y solo en esta pantalla.
 * Google entrega un ID token que la API verifica (firma, `aud`, `hd = trulab.co`, rol).
 */
import { useEffect, useRef, useState } from "react";

import { env } from "@/lib/env";

const SCRIPT_GIS = "https://accounts.google.com/gsi/client";

interface RespuestaCredencial {
  credential?: string;
}

interface GoogleIdentity {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (respuesta: RespuestaCredencial) => void;
        hd?: string;
        ux_mode?: "popup";
        auto_select?: boolean;
      }) => void;
      renderButton: (elemento: HTMLElement, opciones: Record<string, unknown>) => void;
    };
  };
}

declare global {
  interface Window {
    google?: GoogleIdentity;
  }
}

let cargaScript: Promise<GoogleIdentity> | null = null;

function cargarGoogle(): Promise<GoogleIdentity> {
  if (window.google) return Promise.resolve(window.google);
  cargaScript ??= new Promise<GoogleIdentity>((resolver, rechazar) => {
    const script = document.createElement("script");
    script.src = SCRIPT_GIS;
    script.async = true;
    script.defer = true;
    script.onload = () => (window.google ? resolver(window.google) : rechazar(new Error("GIS")));
    script.onerror = () => {
      cargaScript = null;
      rechazar(new Error("No se pudo cargar Google Identity Services"));
    };
    document.head.appendChild(script);
  });
  return cargaScript;
}

export function BotonGoogle({
  alObtenerToken,
  deshabilitado,
}: {
  alObtenerToken: (idToken: string) => void;
  deshabilitado?: boolean;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  // El callback de Google se registra una vez: lee la versión más reciente desde la ref.
  const callback = useRef(alObtenerToken);
  useEffect(() => {
    callback.current = alObtenerToken;
  });

  useEffect(() => {
    if (!env.googleClientId) return;
    let vigente = true;
    cargarGoogle()
      .then((google) => {
        if (!vigente || !contenedor.current) return;
        google.accounts.id.initialize({
          client_id: env.googleClientId,
          hd: "trulab.co",
          ux_mode: "popup",
          callback: (respuesta) => {
            if (respuesta.credential) callback.current(respuesta.credential);
          },
        });
        google.accounts.id.renderButton(contenedor.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: "signin_with",
          shape: "rectangular",
          logo_alignment: "left",
          width: contenedor.current.offsetWidth || 320,
          locale: "es",
        });
      })
      .catch(() => {
        if (vigente) setError(true);
      });
    return () => {
      vigente = false;
    };
  }, []);

  if (!env.googleClientId) {
    return (
      <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
        El ingreso con Google todavía no está configurado en este entorno.
      </p>
    );
  }
  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        No se pudo cargar el ingreso con Google. Revise su conexión y recargue la página.
      </p>
    );
  }
  return (
    <div
      ref={contenedor}
      aria-disabled={deshabilitado || undefined}
      className={deshabilitado ? "pointer-events-none min-h-11 opacity-50" : "min-h-11"}
      data-testid="boton-google"
    />
  );
}
