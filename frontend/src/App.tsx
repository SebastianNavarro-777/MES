import { useEffect, useState } from "react";

// Minimal landing page for the staging skeleton. It reads /healthz so a
// human (or QA Smoke screenshot) can see backend connectivity at a glance.
// Real screens arrive with the frontend Stories under NSG-14.
export default function App() {
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    fetch("/healthz")
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: { status?: string }) => setHealth(data.status ?? "unknown"))
      .catch(() => setHealth("unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>NSG MES</h1>
      <p>Staging stand is up.</p>
      <p>
        Backend health: <strong data-testid="health-status">{health}</strong>
      </p>
    </main>
  );
}
