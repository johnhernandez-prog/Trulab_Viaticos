/**
 * Módulos del menú (docs/user-flows.md F-11, docs/design-system.md §12 y §15). Cada uno declara el
 * permiso que lo muestra: el menú se filtra con los `permisos` de `/me`, que salen de la matriz
 * RBAC del backend (una sola fuente de verdad).
 */
import {
  Briefcase,
  ChartPie,
  ClipboardCheck,
  CreditCard,
  FileText,
  FolderCog,
  Receipt,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { Permiso } from "@/features/auth/contexto";

export interface Modulo {
  ruta: string;
  etiqueta: string;
  icono: LucideIcon;
  /** `null`: visible para cualquier usuario autenticado. */
  permiso: Permiso | null;
  descripcion: string;
}

export const MODULOS: readonly Modulo[] = [
  {
    ruta: "/viaticos",
    etiqueta: "Viáticos",
    icono: FileText,
    permiso: "viaticos:leer_propios",
    descripcion: "Solicitudes y legalizaciones de viáticos.",
  },
  {
    ruta: "/revision",
    etiqueta: "Revisión",
    icono: ClipboardCheck,
    permiso: "viaticos:aprobar",
    descripcion: "Viáticos pendientes de aprobar, devolver o rechazar.",
  },
  {
    ruta: "/pagos",
    etiqueta: "Pagos",
    icono: CreditCard,
    permiso: "pagos:leer",
    descripcion: "Saldos por reembolsar o reintegrar y estado financiero.",
  },
  {
    ruta: "/indicadores",
    etiqueta: "Indicadores",
    icono: ChartPie,
    permiso: "indicadores:leer",
    descripcion: "Consumo por proyecto y estados de los viáticos.",
  },
  {
    ruta: "/cargos",
    etiqueta: "Cargos",
    icono: Briefcase,
    permiso: "cargos:leer",
    descripcion: "Cargos de los colaboradores.",
  },
  {
    ruta: "/usuarios",
    etiqueta: "Usuarios",
    icono: Users,
    permiso: "usuarios:gestionar_operativos",
    descripcion: "Usuarios, roles y accesos.",
  },
  {
    ruta: "/tarifas",
    etiqueta: "Tarifas",
    icono: Receipt,
    permiso: "tarifas:leer",
    descripcion: "Tarifas de viáticos por ciudad y tipo de vinculación.",
  },
  {
    ruta: "/catalogos",
    etiqueta: "Catálogos",
    icono: FolderCog,
    permiso: "catalogos:gestionar",
    descripcion: "Proyectos, rubros y células.",
  },
];

export const PERFIL: Modulo = {
  ruta: "/perfil",
  etiqueta: "Perfil",
  icono: UserRound,
  permiso: null,
  descripcion: "Sus datos y su acceso.",
};

export function modulosVisibles(tiene: (permiso: Permiso) => boolean): Modulo[] {
  return MODULOS.filter((m) => m.permiso === null || tiene(m.permiso));
}

/** Máximo de destinos en la BottomBar antes de agrupar el resto en "Más". */
export const MAXIMO_BARRA_INFERIOR = 4;

/**
 * Reparto de la BottomBar: hasta 4 destinos; si hay más, los 3 primeros y "Más" con el resto.
 * El perfil siempre está disponible (en la barra o dentro de "Más").
 */
export function repartirBarraInferior(visibles: Modulo[]): { barra: Modulo[]; mas: Modulo[] } {
  const todos = [...visibles, PERFIL];
  if (todos.length <= MAXIMO_BARRA_INFERIOR) return { barra: todos, mas: [] };
  const enBarra = MAXIMO_BARRA_INFERIOR - 1;
  return { barra: todos.slice(0, enBarra), mas: todos.slice(enBarra) };
}
