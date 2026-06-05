import {
  Navigate,
  RouterProvider,
  createBrowserRouter,
} from "react-router-dom";
import { OrderDetailPage } from "./features/orders/OrderDetailPage";
import { messages } from "./i18n/es-MX";

const router = createBrowserRouter([
  {
    path: "/",
    // Convenience landing for local dev / E2E; real navigation comes from the
    // (not-yet-built) orders list screen.
    element: <Navigate to="/orders/OF-1001" replace />,
  },
  {
    path: "/orders/:orderId",
    element: <OrderDetailPage />,
  },
  {
    path: "*",
    element: (
      <main style={{ padding: "var(--space-6)" }}>
        <h1>{messages.order.notFound.title}</h1>
      </main>
    ),
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
