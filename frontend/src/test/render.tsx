/**
 * Test render helper (spec §5 F1, day 0): a fresh QueryClient (retry off) + a MemoryRouter.
 *
 *   renderWithProviders(undefined, { route: "/app/relatorio/resumo" })      // the whole App at a route
 *   renderWithProviders(<Desvios />, { route: "/app/desvios?cmp=ac_fc" })   // one page
 *   renderWithProviders(<Relatorio />, { route: "/app/relatorio/gap", path: "/app/relatorio/:capitulo" })
 *
 * Combine with `mockApi` for the network. The filter store is reset before each render unless
 * `resetFilters: false`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation, type Location } from "react-router-dom";

import App from "../App";
import { useFilters } from "../hooks/useFilters";

export interface RenderOptions {
  /** Initial URL (path + query). Default "/". */
  route?: string;
  /** Route pattern to mount `ui` on (needed by pages that read `useParams`). */
  path?: string;
  /** Default true: clears `useFilters` before rendering. */
  resetFilters?: boolean;
}

export interface RenderWithProvidersResult extends RenderResult {
  queryClient: QueryClient;
  /** Current router location (updated on every navigation). */
  location: () => Location;
}

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui?: ReactElement,
  { route = "/", path, resetFilters = true }: RenderOptions = {},
): RenderWithProvidersResult {
  if (resetFilters) useFilters.setState({ filters: {}, measure: "revenue" });
  const queryClient = createTestQueryClient();
  let current: Location | null = null;
  function LocationProbe() {
    current = useLocation();
    return null;
  }
  const content = ui ?? <App />;
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        {path ? (
          <Routes>
            <Route path={path} element={content} />
          </Routes>
        ) : (
          content
        )}
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return {
    ...result,
    queryClient,
    location: () => {
      if (!current) throw new Error("renderWithProviders: localização indisponível");
      return current;
    },
  };
}
