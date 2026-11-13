import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../auth";
import { LoginDialog } from "../../components/LoginDialog";
import { Avatar, Brand, Button, LogoutButton, Spinner } from "../../components/ui";

// Trang quản trị tách riêng (/admin): thanh bên riêng, chỉ tài khoản có email trong ADMIN_EMAILS vào được.

const TABS = [
  { to: "/admin", label: "Tổng quan", end: true },
  { to: "/admin/logs", label: "Hội thoại" },
  { to: "/admin/config", label: "Cấu hình" },
  { to: "/admin/users", label: "Người dùng" },
];

export function AdminLayout() {
  const { user, loading, signOut } = useAuth();
  const [loginOpen, setLoginOpen] = useState(false);

  if (loading) return <Spinner />;

  if (!user || user.role !== "admin") {
    return (
      <div className="grid h-full place-items-center p-4">
        <div className="flex w-full max-w-sm flex-col gap-3 rounded-[14px] border border-line bg-surface p-6 text-center">
          <Brand subtitle="Trang quản trị" className="justify-center" />
          <p className="text-sm text-muted">
            {user ? `Tài khoản ${user.email} không có quyền quản trị.` : "Đăng nhập bằng tài khoản quản trị để tiếp tục."}
          </p>
          {user ? (
            <Button onClick={signOut}>Đăng nhập tài khoản khác</Button>
          ) : (
            <Button variant="primary" onClick={() => setLoginOpen(true)}>
              Đăng nhập
            </Button>
          )}
          <Link to="/" className="text-[13px] text-pine underline underline-offset-2">
            ← Về trang hỏi đáp
          </Link>
        </div>
        <LoginDialog open={loginOpen} onClose={() => setLoginOpen(false)} title="Đăng nhập quản trị" />
      </div>
    );
  }

  return (
    <div className="grid h-full grid-cols-[264px_minmax(0,1fr)] max-[900px]:h-auto max-[900px]:min-h-full max-[900px]:grid-cols-1">
      <nav aria-label="Quản trị" className="flex min-w-0 flex-col gap-5 border-r border-line bg-surface px-4 pt-6 max-[900px]:gap-3 max-[900px]:border-b max-[900px]:border-r-0">
        <Brand subtitle="Trang quản trị" />
        <div className="flex flex-col gap-1 max-[900px]:flex-row max-[900px]:flex-wrap">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 font-medium ${isActive ? "bg-pine-soft text-pine" : "text-muted hover:bg-user"}`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </div>
        <div className="flex-1 max-[900px]:hidden" />
        <Link to="/" className="px-3 text-[13px] text-pine underline-offset-2 hover:underline">
          ← Về trang hỏi đáp
        </Link>
        <div className="-mx-4 flex min-w-0 items-center gap-3 border-t border-line px-4 py-4">
          <Avatar name={user.name} />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5 leading-tight">
            <b className="truncate text-[14px] font-semibold">{user.name}</b>
            <span className="truncate text-xs text-muted">{user.email}</span>
          </div>
          <LogoutButton onClick={signOut} />
        </div>
      </nav>
      <main className="min-w-0 overflow-auto px-6 py-6 max-[900px]:px-4">
        <div className="mx-auto flex max-w-[1000px] flex-col gap-5">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
