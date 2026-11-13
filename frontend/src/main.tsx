import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import "./index.css";
import { ChatPage } from "./pages/ChatPage";
import { AdminLayout } from "./pages/admin/AdminLayout";
import { Config } from "./pages/admin/Config";
import { Logs } from "./pages/admin/Logs";
import { Overview } from "./pages/admin/Overview";
import { Users } from "./pages/admin/Users";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Overview />} />
            <Route path="logs" element={<Logs />} />
            <Route path="config" element={<Config />} />
            <Route path="users" element={<Users />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
);
