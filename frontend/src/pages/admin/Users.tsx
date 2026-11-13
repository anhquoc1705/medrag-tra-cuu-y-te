import { useState } from "react";
import { api } from "../../api";
import { Button, Chip, ErrorNote, Spinner } from "../../components/ui";
import { dateTime } from "../../labels";
import { Panel, PageHead, td, tdNum, th, useApi } from "./common";

interface UserRow {
  id: number;
  email: string;
  name: string;
  role: "user" | "admin";
  disabled: boolean;
  login: ("google" | "email")[];
  created_at: string;
  last_seen_at: string | null;
  conversations: number;
}

export function Users() {
  const { data, setData, error, loading } = useApi<UserRow[]>("/admin/users");
  const [actionError, setActionError] = useState<string | null>(null);

  async function toggle(u: UserRow) {
    if (!window.confirm(`${u.disabled ? "Mở khoá" : "Khoá"} tài khoản ${u.email}?`)) return;
    setActionError(null);
    try {
      const r = await api<{ id: number; disabled: boolean }>(`/admin/users/${u.id}`, { method: "PATCH", body: { disabled: !u.disabled } });
      setData((rows) => rows?.map((x) => (x.id === r.id ? { ...x, disabled: r.disabled } : x)) ?? rows);
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  return (
    <>
      <PageHead
        title="Người dùng"
        sub="Tài khoản đã đăng ký. Khách không có tài khoản nên không có ở đây. Vai trò quản trị đặt bằng ADMIN_EMAILS trong .env."
      />
      <Panel>
        {(error || actionError) && <ErrorNote>{error ?? actionError}</ErrorNote>}
        {loading && !data && <Spinner />}
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-[13px]">
              <thead>
                <tr>
                  <th className={th}>Tài khoản</th>
                  <th className={th}>Vai trò</th>
                  <th className={th}>Đăng nhập bằng</th>
                  <th className={th}>Ngày tạo</th>
                  <th className={th}>Cuộc hỏi đáp</th>
                  <th className={th}>Hoạt động gần nhất</th>
                  <th className={th} />
                </tr>
              </thead>
              <tbody>
                {data.map((u) => (
                  <tr key={u.id} className={u.disabled ? "opacity-60" : ""}>
                    <td className={td}>
                      <b className="font-medium">{u.name}</b>
                      <span className="block text-xs text-muted">{u.email}</span>
                    </td>
                    <td className={td}>
                      {u.role === "admin" ? <Chip tone="ok">Quản trị</Chip> : <Chip tone="info">Người dùng</Chip>}
                      {u.disabled && (
                        <span className="ml-1">
                          <Chip tone="bad">Đã khoá</Chip>
                        </span>
                      )}
                    </td>
                    <td className={td}>{u.login.map((m) => (m === "google" ? "Google" : "Email")).join(" + ")}</td>
                    <td className={tdNum}>{dateTime(u.created_at)}</td>
                    <td className={tdNum}>{u.conversations}</td>
                    <td className={tdNum}>{u.last_seen_at ? dateTime(u.last_seen_at) : "–"}</td>
                    <td className={td}>
                      {u.role !== "admin" && (
                        <Button variant="ghost" onClick={() => toggle(u)}>
                          {u.disabled ? "Mở khoá" : "Khoá"}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {!data.length && (
                  <tr>
                    <td colSpan={7} className={`${td} text-center text-muted`}>
                      Chưa có tài khoản nào.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
