import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../../api/http";

/**
 * AC-3 / AC-4: example query exercising the typed client end-to-end.
 *
 * It calls the generated `/health/` operation (no hardcoded URL) and exposes
 * the query so a component can render differentiated loading / success / error
 * states. NSG-20 will follow this exact shape for the orders list.
 */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async ({ signal }) => {
      const { data, error } = await apiClient.GET("/health/", { signal });
      if (error !== undefined) {
        throw new Error("Health check failed");
      }
      return data;
    },
  });
}
