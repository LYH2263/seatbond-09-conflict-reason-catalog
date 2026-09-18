import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

type Conflict = {
  id: number;
  showtime_id: number;
  party_size: number;
  reason_code: string;
  reason: string;
  reason_description?: string | null;
  retry_recommended?: boolean | null;
  created_at: string;
};

type ReasonCode = {
  code: string;
  description_zh: string;
  retry_recommended: boolean;
  enabled: boolean;
};

export default function ConflictsPage() {
  const [rows, setRows] = useState<Conflict[]>([]);
  const [codes, setCodes] = useState<ReasonCode[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [busyCode, setBusyCode] = useState<string>("");

  const loadCodes = useCallback(() => {
    api<ReasonCode[]>("/reason-codes").then(setCodes).catch(() => setCodes([]));
  }, []);

  const loadConflicts = useCallback((code: string) => {
    const qs = code ? `?reason_code=${encodeURIComponent(code)}` : "";
    api<Conflict[]>(`/conflicts${qs}`).then(setRows).catch(() => setRows([]));
  }, []);

  useEffect(() => {
    loadCodes();
  }, [loadCodes]);

  useEffect(() => {
    loadConflicts(filter);
  }, [filter, loadConflicts]);

  async function toggle(code: ReasonCode) {
    setBusyCode(code.code);
    try {
      await api<ReasonCode>(`/reason-codes/${code.code}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !code.enabled }),
      });
      loadCodes();
    } finally {
      setBusyCode("");
    }
  }

  return (
    <>
      <h2>冲突</h2>
      <div className="toolbar">
        <label>
          原因码{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">全部</option>
            {codes.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code}
                {c.enabled ? "" : "（已停用）"} · {c.description_zh}
              </option>
            ))}
          </select>
        </label>
        <span className="hint">共 {rows.length} 条冲突日志</span>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>时间</th>
            <th>场次</th>
            <th>人数</th>
            <th>原因码</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td className="mono">{new Date(c.created_at).toLocaleString()}</td>
              <td>{c.showtime_id}</td>
              <td>{c.party_size}</td>
              <td>
                <span className="chip mono" title={c.reason_description || ""}>
                  {c.reason_code}
                </span>
                {c.retry_recommended && <span className="retry-tag">建议重试</span>}
              </td>
              <td>{c.reason_description || c.reason}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="hint">
                暂无冲突记录
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 className="panel-title">原因码目录</h3>
      <table className="table catalog">
        <thead>
          <tr>
            <th>代码</th>
            <th>中文说明</th>
            <th>建议重试</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {codes.map((c) => (
            <tr key={c.code} className={c.enabled ? "" : "row-off"}>
              <td className="mono">{c.code}</td>
              <td>{c.description_zh}</td>
              <td>{c.retry_recommended ? "是" : "否"}</td>
              <td>
                <span className={`dot${c.enabled ? " dot-on" : ""}`} />
                {c.enabled ? "启用" : "停用"}
              </td>
              <td>
                <button
                  className="mini"
                  disabled={busyCode === c.code}
                  onClick={() => toggle(c)}
                >
                  {busyCode === c.code ? "…" : c.enabled ? "停用" : "启用"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
