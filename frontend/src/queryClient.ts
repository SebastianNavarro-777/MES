import { QueryClient } from "@tanstack/react-query";

/**
 * AC-3: a single application-wide QueryClient with sensible defaults.
 *
 * NSG-20 (orders list) relies on this cache plus TanStack Query's automatic
 * cancellation/discarding of stale requests, so the defaults are set once here
 * rather than per-query.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Treat data as fresh for 30s to avoid refetch storms on remount.
      staleTime: 30_000,
      // Retry transient failures a couple of times with backoff.
      retry: 2,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
