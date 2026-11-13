// Matchers de Testing Library para Vitest (`toBeInTheDocument`, `toHaveTextContent`...).
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { guardarAccessToken } from "@/lib/sesion";

// jsdom define su propio `AbortSignal`, pero `Request` es el de Node (undici), que rechaza esa
// señal: React Router crea un `Request` con `signal` en cada navegación del router de datos. Las
// pruebas no usan loaders ni acciones, así que se omite la señal solo en este entorno.
class RequestSinSenal extends globalThis.Request {
  constructor(entrada: RequestInfo | URL, init?: RequestInit) {
    const { signal: _omitida, ...resto } = init ?? {};
    super(entrada, resto);
  }
}
globalThis.Request = RequestSinSenal;

afterEach(() => {
  cleanup();
  // El access token vive en memoria del módulo: no debe pasar de una prueba a otra.
  guardarAccessToken(null);
});
