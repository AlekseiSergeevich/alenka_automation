import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { LoginPage } from "@/pages/LoginPage";
import { StoresPage } from "@/pages/StoresPage";
import { StorePage } from "@/pages/StorePage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { OrderBlankPage } from "@/pages/OrderBlankPage";

import { useEffect } from "react";

export function App() {
  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimer: NodeJS.Timeout;

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/ws/logs`);
      
      ws.onmessage = (event) => {
        console.log("%c[Backend]", "color: #ff00ff; font-weight: bold", event.data);
      };
      
      ws.onclose = () => {
        // Try to reconnect after 2 seconds
        reconnectTimer = setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null; // Prevent reconnect loop on unmount
        ws.close();
      }
    };
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/stores" replace />} />
        <Route path="stores" element={<StoresPage />} />
        <Route path="stores/:storeId" element={<StorePage />} />
        <Route path="order-blank" element={<OrderBlankPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
