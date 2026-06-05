import { useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { ManufacturingOrderDto } from "../../api/orders";
import { ORDER_TRANSITION_ACTION, messages } from "../../i18n/es-MX";
import { getAvailableTransitions } from "./orderStatus";
import type { OrderStatusValue } from "./orderStatus";
import { StatusPill } from "./StatusPill";
import { TransitionConfirmModal } from "./TransitionConfirmModal";
import { useOrder } from "./useOrder";
import { useTransitionOrder } from "./useTransitionOrder";
import "./OrderDetailPage.css";

export function OrderDetailPage() {
  const { orderId = "" } = useParams<{ orderId: string }>();
  const query = useOrder(orderId);
  const mutation = useTransitionOrder(orderId);
  const [pendingTarget, setPendingTarget] = useState<OrderStatusValue | null>(
    null,
  );

  if (query.isPending) {
    return (
      <main className="order-detail">
        <p className="order-detail__status" role="status">
          {messages.order.loading}
        </p>
      </main>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.isNotFound;
    if (notFound) {
      return (
        <main className="order-detail">
          <section className="order-detail__feedback" data-testid="order-not-found">
            <h1 className="order-detail__feedback-title">
              {messages.order.notFound.title}
            </h1>
            <p>{messages.order.notFound.body}</p>
          </section>
        </main>
      );
    }
    return (
      <main className="order-detail">
        <section className="order-detail__feedback" data-testid="order-error">
          <h1 className="order-detail__feedback-title">
            {messages.order.error.title}
          </h1>
          <p>{messages.order.error.body}</p>
          <button
            type="button"
            className="btn btn--secondary"
            onClick={() => void query.refetch()}
          >
            {messages.order.error.retry}
          </button>
        </section>
      </main>
    );
  }

  const order: ManufacturingOrderDto = query.data;
  const transitions = getAvailableTransitions(order.status);

  function handleConfirm() {
    if (pendingTarget === null) {
      return;
    }
    mutation.mutate(pendingTarget, {
      onSuccess: () => setPendingTarget(null),
    });
  }

  function handleCancel() {
    setPendingTarget(null);
    mutation.reset();
  }

  function openTransition(target: OrderStatusValue) {
    mutation.reset();
    setPendingTarget(target);
  }

  return (
    <main className="order-detail">
      <header className="order-detail__header">
        <p className="order-detail__eyebrow">{messages.order.detailHeading}</p>
        <h1 className="order-detail__id">{order.id}</h1>
        <StatusPill status={order.status} />
      </header>

      <section className="order-detail__card" aria-label={messages.order.detailHeading}>
        <dl className="order-detail__fields">
          <Field label={messages.order.fields.id} value={order.id} />
          <Field label={messages.order.fields.product} value={order.product_name} />
          <Field
            label={messages.order.fields.qty}
            value={String(order.qty)}
          />
          <Field label={messages.order.fields.route} value={order.route} />
          <Field
            label={messages.order.fields.dueDate}
            value={formatDate(order.due_date)}
          />
        </dl>
      </section>

      <section className="order-detail__transitions" aria-label={messages.order.transitions.heading}>
        <h2 className="order-detail__section-title">
          {messages.order.transitions.heading}
        </h2>
        {transitions.length === 0 ? (
          <p className="order-detail__muted">{messages.order.transitions.none}</p>
        ) : (
          <div className="order-detail__transition-buttons">
            {transitions.map((target) => (
              <button
                key={target}
                type="button"
                className="btn btn--primary"
                onClick={() => openTransition(target)}
                data-testid={`transition-${target}`}
              >
                {ORDER_TRANSITION_ACTION[target]}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Extension slot for NSG-41 (WIP balances). Kept as a stable container
          so the WIP panel can mount here without refactoring this screen. */}
      <section
        className="order-detail__wip-slot"
        data-slot="wip-panel"
        aria-label="Balances de WIP"
      />

      {pendingTarget !== null && (
        <TransitionConfirmModal
          fromStatus={order.status}
          toStatus={pendingTarget}
          isSubmitting={mutation.isPending}
          errorMessage={
            mutation.isError ? messages.order.transitionError.generic : null
          }
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </main>
  );
}

interface FieldProps {
  readonly label: string;
  readonly value: string;
}

function Field({ label, value }: FieldProps) {
  return (
    <div className="order-detail__field">
      <dt className="order-detail__field-label">{label}</dt>
      <dd className="order-detail__field-value">{value}</dd>
    </div>
  );
}

function formatDate(isoDate: string): string {
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) {
    return isoDate;
  }
  return new Intl.DateTimeFormat("es-MX", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(parsed);
}
