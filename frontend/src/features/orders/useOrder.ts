import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { fetchOrder } from "../../api/orders";
import { orderKeys } from "./queryKeys";

/**
 * Fetch + cache a single order's detail. A 404 is surfaced as a normal query
 * error (an `ApiError` with `isNotFound`) so the screen can render a dedicated
 * "not found" state rather than retrying forever.
 */
export function useOrder(orderId: string) {
  return useQuery({
    queryKey: orderKeys.detail(orderId),
    queryFn: () => fetchOrder(orderId),
    // Do not retry client errors (404 etc.); only transient/5xx are worth a retry.
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status < 500) {
        return false;
      }
      return failureCount < 2;
    },
  });
}
