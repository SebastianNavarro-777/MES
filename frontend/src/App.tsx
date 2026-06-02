import { HealthStatus } from "./features/health/HealthStatus";

export function App() {
  return (
    <main>
      <h1>NSG MES</h1>
      <p>Manufacturing Execution System — frontend scaffold.</p>
      <section aria-label="Backend connectivity">
        <HealthStatus />
      </section>
    </main>
  );
}
