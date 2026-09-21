import { format, isAfter, isBefore, parseISO } from "date-fns";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useCallLogs } from "../api/calls";
import { useCustomers } from "../api/customers";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Drawer } from "../components/ui/Drawer";
import { LiveDuration } from "../components/ui/LiveDuration";
import { Skeleton } from "../components/ui/Skeleton";
import type { CallLog } from "../types";
import { formatDuration } from "../utils/formatDuration";
import { callFullSummary, callQuickSummary } from "../utils/callSummary";
import { isLiveStatus, normalizedStatus, statusTone } from "../utils/statusBadge";
import "./Calls.css";

function parsed(value?: string | null): Date | null {
  if (!value) return null;
  const date = parseISO(value.replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function DurationCell({ log }: { log: CallLog }) {
  const live = isLiveStatus(log.status, log.call_status, log.created_at);
  if (live) return (
    <span className="flex items-center gap-1.5">
      <span className="live-dot" />
      <LiveDuration createdAt={log.created_at} />
    </span>
  );
  return <>{formatDuration(log.duration)}</>;
}

export function Calls() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [statusFilter, setStatusFilter] = useState("");
  const [alertsOnly, setAlertsOnly] = useState(searchParams.get("alerts") === "1");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [selected, setSelected] = useState<CallLog | null>(null);

  const initialCalls = useCallLogs(false);
  const hasLive = (initialCalls.data || []).some((log) => isLiveStatus(log.status, log.call_status, log.created_at));
  const calls = useCallLogs(hasLive ? 5000 : false);
  const logs = calls.data || initialCalls.data || [];
  const liveCalls = logs.filter((log) => isLiveStatus(log.status, log.call_status, log.created_at));

  const customers = useCustomers();
  const customerMap = useMemo(() => {
    const map = new Map<number, string>();
    (customers.data || []).forEach((c) => map.set(c.id, c.name));
    return map;
  }, [customers.data]);

  const filtered = useMemo(() => {
    return logs
      .filter((log) => {
        const haystack = [
          log.provider_call_id || log.call_sid || "",
          log.status || "",
          log.call_status || "",
          callFullSummary(log),
          callQuickSummary(log),
          log.customer_id ? (customerMap.get(log.customer_id) || "") : "",
        ]
          .join(" ")
          .toLowerCase();
        if (search && !haystack.includes(search.toLowerCase())) return false;
        if (statusFilter && normalizedStatus(log.status, log.call_status) !== statusFilter) return false;
        if (alertsOnly && !log.is_abnormal) return false;
        const created = parsed(log.created_at);
        if (from && created && isBefore(created, parseISO(from))) return false;
        if (to && created && isAfter(created, parseISO(to))) return false;
        return true;
      })
      .sort((a, b) => {
        const ta = parsed(a.created_at)?.getTime() || 0;
        const tb = parsed(b.created_at)?.getTime() || 0;
        return tb - ta;
      });
  }, [logs, search, statusFilter, alertsOnly, from, to, customerMap]);

  const uniqueStatuses = useMemo(
    () => Array.from(new Set(logs.map((log) => normalizedStatus(log.status, log.call_status)))).sort(),
    [logs]
  );

  if (initialCalls.isLoading) return <Skeleton className="h-[70vh]" />;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Calls</h1>
          <p className="text-sm text-slate-500">
            {logs.length} total · filter, inspect transcripts, and watch live calls.
          </p>
        </div>
      </div>

      {liveCalls.length > 0 && (
        <div className="live-strip mb-4">
          <p className="calls-live-label">
            🔴 {liveCalls.length} live call{liveCalls.length > 1 ? "s" : ""}
          </p>
          {liveCalls.map((log) => (
            <button
              key={log.id}
              className="flex min-w-56 items-center gap-3 rounded-xl bg-white px-4 py-3 text-left shadow-sm transition hover:shadow-md"
              onClick={() => setSelected(log)}
            >
              <span className="live-dot" />
              <span>
                <strong className="block text-sm font-bold text-slate-900">
                  {log.customer_id ? (customerMap.get(log.customer_id) || `Call #${log.id}`) : `Call #${log.id}`}
                </strong>
                <small className="text-xs font-semibold text-amber-700">
                  LIVE · <LiveDuration createdAt={log.created_at} />
                </small>
              </span>
            </button>
          ))}
        </div>
      )}

      <Card>
        <div className="calls-filters">
          <label className="relative">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
            <input
              className="field pl-9"
              placeholder="Search calls, SID, customer…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <select className="field" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            {uniqueStatuses.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-600">
            <input
              type="checkbox"
              checked={alertsOnly}
              onChange={(e) => setAlertsOnly(e.target.checked)}
            />
            Alerts only
          </label>
          <input className="field" type="date" value={from} onChange={(e) => setFrom(e.target.value)} title="From date" />
          <input className="field" type="date" value={to} onChange={(e) => setTo(e.target.value)} title="To date" />
        </div>

        {/* Desktop table */}
        <div className="calls-table table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Provider call ID</th>
                <th>Status</th>
                <th>Lead</th>
                <th>Health</th>
                <th title="Recorded by the telephony provider when the call ends.">Duration ⓘ</th>
                <th>Created</th>
                <th>Call summary</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-sm text-slate-400">
                    No calls match your filters.
                  </td>
                </tr>
              )}
              {filtered.map((log) => (
                <tr
                  key={log.id}
                  className="cursor-pointer transition hover:bg-slate-50"
                  onClick={() => navigate(`/calls/${log.id}`)}
                >
                  <td className="font-semibold text-slate-900">
                    {log.customer_id ? (customerMap.get(log.customer_id) || `#${log.customer_id}`) : "--"}
                  </td>
                  <td className="max-w-[160px] truncate font-mono text-xs text-slate-500">
                    {log.provider_call_id || log.call_sid || `#${log.id}`}
                  </td>
                  <td>
                    <Badge tone={statusTone(log.status, log.call_status)}>
                      {normalizedStatus(log.status, log.call_status)}
                    </Badge>
                  </td>
                  <td>
                    {log.qualification && (
                      <Badge tone={
                        log.qualification === "hot" ? "green" :
                        log.qualification === "warm" ? "amber" :
                        log.qualification === "cold" ? "red" : "gray"
                      }>
                        {log.qualification}
                      </Badge>
                    )}
                  </td>
                  <td>
                    <Badge tone={log.is_abnormal ? "red" : "green"}>
                      {log.is_abnormal ? "Review" : "Normal"}
                    </Badge>
                  </td>
                  <td className="font-semibold tabular-nums">
                    <DurationCell log={log} />
                  </td>
                  <td className="whitespace-nowrap text-slate-500">
                    {parsed(log.created_at) ? format(parsed(log.created_at) as Date, "PP p") : "--"}
                  </td>
                  <td className="max-w-xs truncate text-slate-500">{callQuickSummary(log)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile cards */}
        <div className="space-y-3 md:hidden">
          {filtered.map((log) => (
            <button
              key={log.id}
              className="w-full rounded-xl border border-slate-100 bg-white p-4 text-left shadow-sm"
              onClick={() => setSelected(log)}
            >
              <div className="flex items-center justify-between">
                <Badge tone={statusTone(log.status, log.call_status)}>
                  {normalizedStatus(log.status, log.call_status)}
                </Badge>
                <span className="text-sm font-bold tabular-nums">
                  <DurationCell log={log} />
                </span>
              </div>
              <p className="mt-2 font-semibold text-slate-900">
                {log.customer_id ? (customerMap.get(log.customer_id) || `Call #${log.id}`) : `Call #${log.id}`}
              </p>
              <p className="mt-1 truncate text-xs text-slate-500">{callQuickSummary(log)}</p>
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="py-8 text-center text-sm text-slate-400">No calls match your filters.</p>
          )}
        </div>
      </Card>

      <Drawer title="Call detail" open={Boolean(selected)} onClose={() => setSelected(null)}>
        {selected && (
          <div className="space-y-4">

            {/* Status + duration + lead tier row */}
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(selected.status, selected.call_status)}>
                {normalizedStatus(selected.status, selected.call_status)}
              </Badge>
              {selected.qualification && (
                <Badge tone={
                  selected.qualification === "hot" ? "green" :
                  selected.qualification === "warm" ? "amber" :
                  selected.qualification === "cold" ? "red" : "gray"
                }>
                  {selected.qualification === "hot" ? "🔥 Hot Lead" :
                   selected.qualification === "warm" ? "☀️ Warm Lead" :
                   selected.qualification === "cold" ? "❄️ Cold Lead" : "Unqualified"}
                </Badge>
              )}
              <span className="ml-auto text-sm font-bold tabular-nums text-slate-700">
                <DurationCell log={selected} />
              </span>
            </div>

            {/* Quick summary — most important, shown first */}
            {callQuickSummary(selected) && (
              <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3">
                <p className="text-xs font-bold uppercase tracking-wide text-indigo-500 mb-1">Outcome</p>
                <p className="text-sm font-semibold text-indigo-900">{callQuickSummary(selected)}</p>
              </div>
            )}

            {selected.is_abnormal && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3">
                <p className="mb-1 text-xs font-bold uppercase tracking-wide text-red-600">Guardrail alert</p>
                <p className="text-sm font-semibold text-red-900">
                  {(selected.abnormal_reasons || []).map((reason) => reason.replace(/_/g, " ")).join(", ")}
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4 text-sm">
              <div><p className="label">Turns / minute</p><p className="font-semibold">{selected.turns_per_minute ?? "--"}</p></div>
              <div><p className="label">Interruptions</p><p className="font-semibold">{selected.interruption_count ?? 0}</p></div>
              <div><p className="label">False turns</p><p className="font-semibold">{selected.false_turn_count ?? 0}</p></div>
              <div><p className="label">Estimated ₹ / minute</p><p className="font-semibold">{selected.estimated_cost_per_minute_inr != null ? `₹${selected.estimated_cost_per_minute_inr.toFixed(2)}` : "--"}</p></div>
            </div>

            {/* Lead score bar */}
            {selected.lead_score != null && (
              <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Lead Score</p>
                  <span className="text-sm font-extrabold text-slate-900">{selected.lead_score}/100</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all"
                    style={{ width: `${selected.lead_score}%` }}
                  />
                </div>
              </div>
            )}

            {/* Call meta */}
            <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4 text-sm">
              <div>
                <p className="label">Customer</p>
                <p className="font-semibold text-slate-900">
                  {selected.customer_id ? (customerMap.get(selected.customer_id) || `#${selected.customer_id}`) : "--"}
                </p>
              </div>
              <div>
                <p className="label">Date & Time</p>
                <p className="font-semibold text-slate-900">
                  {parsed(selected.created_at) ? format(parsed(selected.created_at) as Date, "PPp") : "--"}
                </p>
              </div>
              <div className="col-span-2">
                <p className="label">Provider call ID</p>
                <p className="break-all font-mono text-xs text-slate-600">{selected.provider_call_id || selected.call_sid || "--"}</p>
              </div>
            </div>

            {/* Full summary */}
            {callFullSummary(selected) && (
              <Card>
                <p className="label">AI Summary</p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{callFullSummary(selected)}</p>
              </Card>
            )}

            {/* Transcript */}
            {selected.transcript ? (
              <Card>
                <p className="label">Full Transcript</p>
                <div className="mt-3 space-y-2 text-sm max-h-96 overflow-y-auto">
                  {selected.transcript.split("\n").filter(Boolean).map((line, i) => {
                    const lower = line.toLowerCase();
                    const isAssistant = lower.startsWith("assistant:");
                    const isUser = lower.startsWith("user:") || lower.startsWith("customer:");
                    const label = isAssistant ? "AI" : isUser ? "Customer" : null;
                    const content = line.includes(":") ? line.split(":").slice(1).join(":").trim() : line;
                    return (
                      <div key={i} className={isAssistant
                        ? "transcript-turn transcript-assistant"
                        : isUser ? "transcript-turn transcript-user" : "transcript-turn transcript-unknown"}>
                        {label && (
                          <span className="transcript-speaker">{label}</span>
                        )}
                        <p>{content || line}</p>
                      </div>
                    );
                  })}
                </div>
              </Card>
            ) : (
              <Card>
                <p className="label">Transcript</p>
                <p className="mt-2 text-sm text-slate-400">No transcript recorded yet. The call may still be in progress.</p>
              </Card>
            )}
          </div>
        )}
      </Drawer>
    </>
  );
}
