import { HEALTH_STATUS } from "../../api/enums";
import { useHealth } from "./useHealth";

/**
 * AC-3: renders the three differentiated states of the example query.
 *
 * Until the backend ships a real `/health/` endpoint (NSG-18/NSG-25) this will
 * typically resolve to the error branch in local dev — which still demonstrates
 * that loading, success and error are handled distinctly.
 */
export function HealthStatus() {
  const { isPending, isError, data } = useHealth();

  if (isPending) {
    return (
      <p role="status" data-testid="health-loading">
        Checking backend…
      </p>
    );
  }

  if (isError) {
    return (
      <p role="alert" data-testid="health-error">
        Backend unreachable
      </p>
    );
  }

  const healthy = data.status === HEALTH_STATUS.ok;
  return (
    <p data-testid="health-success">
      Backend status: <strong>{healthy ? "healthy" : "degraded"}</strong>
    </p>
  );
}
