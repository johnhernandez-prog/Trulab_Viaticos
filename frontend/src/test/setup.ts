// Matchers de Testing Library para Vitest (`toBeInTheDocument`, `toHaveTextContent`...).
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
