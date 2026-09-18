import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

type Conflict = {
  id: number;
  showtime_id: number;
  party_size: number;
  reason: string;
  reason_code: string;
  created_at: string;
};

type Reason = {
  code: string;
  description_zh: string;
  suggest_retry: boolean;
  enabled: boolean;
  builtin: boolean;
};

export default function ConflictsPage() {
  const [rows, setRows] = useState<Conflict[]>([]);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [filter, setFilter] = useState("");
  const [showPanel, setShowPanel] = useState(false);
  const [err, setErr] = useState("");

  const loadReasons = useCallback(() => {
    api<Reason[]>("/conflict-reasons").then(setReasons).catch(() => setReasons([]));
  }, []);

  useEffect(() => {
    loadReasons();
  }, [loadReasons]);

  useEffect(() => {
    const q = filter ? `?reason_code=${encodeURIComponent(filter)}` : "";
    api<Conflict[]>(`/conflicts${q}`).then(setRows).catch(() => setRows([]));
  }, [filter]);

  const reasonMap = useMemo(
    () => Object.fromEntries(reasons.map((r) => [r.code, r])) as Record<string, Reason>,
    [reasons],
  );

  async function toggle(code: string, enabled: boolean) {
    setErr("");
    try {
      await api<Reason>(`/conflict-reasons/${encodeURIComponent(code)}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      });
      loadReasons();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <h2>冲突</h2>
      <div className="toolbar">
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">全部原因码</option>
          {reasons.map((r) => (
            <option key={r.code} value={r.code}>
              {r.code} · {r.description_zh}
              {r.enabled ? "" : "（已停用）"}
            </option>
          ))}
        </select>
        <button className="btn-ghost" onClick={() => setShowPanel((v) => !v)}>
          {showPanel ? "收起原因码" : "原因码管理"}
        </button>
      </div>
      {err && <div className="err">{err}</div>}

      {showPanel && (
        <div className="panel">
          <h3>原因码目录</h3>
          <table className="table">
            <thead>
              <tr>
                <th>代码</th>
                <th>说明</th>
                <th>建议重试</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reasons.map((r) => (
                <tr key={r.code}>
                  <td className="mono">{r.code}</td>
                  <td>{r.description_zh}</td>
                  <td>{r.suggest_retry ? "建议" : "不建议"}</td>
                  <td>
                    <span className={`chip ${r.enabled ? "chip--ok" : "chip--off"}`}>
                      {r.enabled ? "启用中" : "已停用"}
                    </span>
                  </td>
                  <td>
                    <button className="btn-ghost" onClick={() => toggle(r.code, !r.enabled)}>
                      {r.enabled ? "停用" : "启用"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <table className="table">
        <thead>
          <tr>
            <th>时间</th>
            <th>场次</th>
            <th>人数</th>
            <th>原因码</th>
            <th>说明</th>
            <th>详情</th>
            <th>重试</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const meta = reasonMap[c.reason_code];
            return (
              <tr key={c.id}>
                <td className="mono">{new Date(c.created_at).toLocaleString()}</td>
                <td>{c.showtime_id}</td>
                <td>{c.party_size}</td>
                <td>
                  <span className="chip chip--code">{c.reason_code}</span>
                </td>
                <td>{meta ? meta.description_zh : "—"}</td>
                <td>{c.reason}</td>
                <td>
                  {meta ? (
                    <span className={`chip ${meta.suggest_retry ? "chip--ok" : "chip--off"}`}>
                      {meta.suggest_retry ? "建议" : "不建议"}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
