import { ORDER_STATUS_PRESENTATION } from "../../i18n/es-MX";
import type { OrderStatusValue } from "./orderStatus";
import "./StatusPill.css";

interface StatusPillProps {
  readonly status: OrderStatusValue;
}

/**
 * Status pill: colour + icon + text, never colour only (docs/ui-design.md).
 * The icon and label make the status perceivable for colourblind operators and
 * under poor lighting.
 */
export function StatusPill({ status }: StatusPillProps) {
  const { label, icon, tier } = ORDER_STATUS_PRESENTATION[status];
  return (
    <span className={`status-pill status-pill--${tier}`} data-testid="status-pill">
      <span className="status-pill__icon" aria-hidden="true">
        {icon}
      </span>
      <span className="status-pill__label">{label}</span>
    </span>
  );
}
