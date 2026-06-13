import type { WipPositionDto } from "../../api/wip";
import { messages } from "../../i18n/es-MX";
import { useWipPositions } from "./useWipPositions";
import "./WipPanel.css";

interface WipPanelProps {
  readonly orderId: string;
}

/**
 * WIP balances panel mounted on the order-detail screen (NSG-41). Reads the
 * `wip` context's projection (`GET /api/v1/wip/positions/?order_id={id}`,
 * ADR 0004) via TanStack Query and renders the net balance per route step.
 *
 * The balance shown is exactly the value returned by the API; the wip domain
 * owns the formula and the UI never recomputes it (NSG-37 AC-1).
 */
export function WipPanel({ orderId }: WipPanelProps) {
  const query = useWipPositions(orderId);

  return (
    <section className="wip-panel" aria-label={messages.wip.heading}>
      <header className="wip-panel__header">
        <h2 className="wip-panel__title">{messages.wip.heading}</h2>
        <p className="wip-panel__subtitle">{messages.wip.subheading}</p>
      </header>

      <WipPanelBody
        isPending={query.isPending}
        isError={query.isError}
        error={query.error}
        positions={query.data}
        onRetry={() => void query.refetch()}
      />
    </section>
  );
}

interface WipPanelBodyProps {
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly error: unknown;
  readonly positions: readonly WipPositionDto[] | undefined;
  readonly onRetry: () => void;
}

function WipPanelBody({
  isPending,
  isError,
  positions,
  onRetry,
}: WipPanelBodyProps) {
  if (isPending) {
    return (
      <p className="wip-panel__status" role="status">
        {messages.wip.loading}
      </p>
    );
  }

  if (isError) {
    return (
      <div className="wip-panel__feedback" role="alert" data-testid="wip-error">
        <p className="wip-panel__feedback-title">{messages.wip.error.title}</p>
        <p className="wip-panel__muted">{messages.wip.error.body}</p>
        <button type="button" className="btn btn--secondary" onClick={onRetry}>
          {messages.wip.error.retry}
        </button>
      </div>
    );
  }

  if (positions === undefined || positions.length === 0) {
    return (
      <p className="wip-panel__muted" data-testid="wip-empty">
        {messages.wip.empty}
      </p>
    );
  }

  return <WipBalancesTable positions={positions} />;
}

function WipBalancesTable({
  positions,
}: {
  readonly positions: readonly WipPositionDto[];
}) {
  const { columns, routeStepPrefix, heading } = messages.wip;
  return (
    <table className="wip-panel__table" data-testid="wip-table">
      <caption className="wip-panel__caption">{heading}</caption>
      <thead>
        <tr>
          <th scope="col">{columns.routeStep}</th>
          <th scope="col" className="wip-panel__num">{columns.qtyIn}</th>
          <th scope="col" className="wip-panel__num">{columns.qtyOut}</th>
          <th scope="col" className="wip-panel__num">{columns.qtyScrap}</th>
          <th scope="col" className="wip-panel__num">{columns.balance}</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((position) => (
          <tr
            key={position.route_step}
            data-testid={`wip-row-${position.route_step}`}
          >
            <th scope="row">
              {routeStepPrefix} {position.route_step}
            </th>
            <td className="wip-panel__num">{position.qty_in}</td>
            <td className="wip-panel__num">{position.qty_out}</td>
            <td className="wip-panel__num">{position.qty_scrap}</td>
            <td className="wip-panel__num wip-panel__balance">
              {position.balance}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
