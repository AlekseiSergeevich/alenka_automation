import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { LoginPage } from "@/pages/LoginPage";
import { StoresPage } from "@/pages/StoresPage";
import { StorePage } from "@/pages/StorePage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { OrderBlankPage } from "@/pages/OrderBlankPage";

export function App() {
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
