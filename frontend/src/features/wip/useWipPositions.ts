import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { fetchWipPositions } from "../../api/wip";
import { wipKeys } from "./queryKeys";

/**
 * Fetch + cache the WIP balances of a single order's route steps. Mirrors the
 * retry policy of `useOrder`: client errors (4xx) are not retried, only
 * transient/5xx responses are. The wip read returns `[]` (never 404) for an
 * order without positions, so the empty case is data, not an error.
 */
export function useWipPositions(orderId: string) {
  return useQuery({
    queryKey: wipKeys.byOrder(orderId),
    queryFn: () => fetchWipPositions(orderId),
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status < 500) {
        return false;
      }
      return failureCount < 2;
    },
  });
}
