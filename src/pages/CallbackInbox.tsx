import { AlertTriangle, CalendarClock, CheckCircle2, Clock3, PhoneCall, Search, UserRound } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { useCallbacks, useCallbackSummary, useUpdateCallback } from "../api/callbacks";
import { api, getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import { StatCard } from "../components/ui/StatCard";
import type { CallbackStatus, CallbackTask, CallbackUpdate } from "../types";

interface TeamMember { id: number; full_name: string; email: string; is_active: boolean }

const statusTone: Record<CallbackStatus, "gray" | "amber" | "green" | "red"> = {
  pending: "amber", assigned: "gray", completed: "green", cancelled: "red",
};

function localInput(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function displayDate(value?: string | null, fallback = "Not scheduled") {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export function CallbackInbox() {
  const [status, setStatus] = useState<CallbackStatus | "">("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<CallbackTask | null>(null);
  const [form, setForm] = useState({
    status: "pending" as CallbackStatus,
    assigned_user_id: "",
    requested_date: "",
    scheduled_at: "",
    notes: "",
  });
  const callbacks = useCallbacks({ status, search });
  const summary = useCallbackSummary();
  const update = useUpdateCallback();
  const team = useQuery({
    queryKey: ["system", "team"],
    queryFn: async () => (await api.get<TeamMember[]>("/system/team")).data,
  });

  useEffect(() => {
    if (!selected) return;
    setForm({
      status: selected.status,
      assigned_user_id: selected.assigned_user_id ? String(selected.assigned_user_id) : "",
      requested_date: selected.requested_date || "",
      scheduled_at: localInput(selected.scheduled_at),
      notes: selected.notes || "",
    });
  }, [selected]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const payload: CallbackUpdate = {
      status: form.status,
      notes: form.notes,
      requested_date: form.requested_date || undefined,
      scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : undefined,
      clear_schedule: !form.scheduled_at,
      assigned_user_id: form.assigned_user_id ? Number(form.assigned_user_id) : undefined,
      clear_assignee: !form.assigned_user_id,
    };
    try {
      const saved = await update.mutateAsync({ id: selected.id, update: payload });
      toast.success("Callback task updated.");
      setSelected(saved);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  if (callbacks.isLoading || summary.isLoading) return <Skeleton className="h-[70vh]" />;

  const totals = summary.data || { pending: 0, assigned: 0, overdue: 0, due_today: 0, completed: 0 };
  return <>
    <div className="page-head">
      <div>
        <h1 className="text-2xl font-extrabold">Callback Inbox</h1>
        <p className="text-sm text-slate-500">Customer-requested follow-ups, owned and tracked to completion.</p>
      </div>
    </div>

    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <StatCard icon={Clock3} label="Pending" value={String(totals.pending)} hint="Waiting for an owner" onClick={() => setStatus("pending")} />
      <StatCard icon={UserRound} label="Assigned" value={String(totals.assigned)} hint="Currently owned" onClick={() => setStatus("assigned")} />
      <StatCard icon={AlertTriangle} label="Overdue" value={String(totals.overdue)} hint="Past scheduled time" />
      <StatCard icon={CheckCircle2} label="Completed" value={String(totals.completed)} hint="Closed follow-ups" onClick={() => setStatus("completed")} />
    </section>

    <Card className="mt-5">
      <div className="calls-filters">
        <label className="relative">
          <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
          <input className="field pl-9" placeholder="Search name, phone, or notes" value={search} onChange={event => setSearch(event.target.value)} />
        </label>
        <select className="field" value={status} onChange={event => setStatus(event.target.value as CallbackStatus | "")}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="assigned">Assigned</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <Button variant="ghost" onClick={() => { setStatus(""); setSearch(""); }}>Clear filters</Button>
      </div>
      {callbacks.isError && <p className="py-8 text-center text-sm text-red-600">{getErrorMessage(callbacks.error)}</p>}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Customer</th><th>Status</th><th>Requested</th><th>Scheduled</th><th>Owner</th><th>Lead</th><th>Action</th></tr></thead>
          <tbody>
            {(callbacks.data || []).map(item => <tr key={item.id}>
              <td><p className="font-bold text-slate-900">{item.customer_name}</p><p className="text-xs text-slate-500">{item.customer_phone || "No phone"}</p></td>
              <td><Badge tone={statusTone[item.status]}>{item.status}</Badge></td>
              <td>{item.requested_date || "Unspecified"}</td>
              <td>{displayDate(item.scheduled_at)}</td>
              <td>{item.assigned_user_name || "Unassigned"}</td>
              <td>{item.qualification || "—"}{item.lead_score != null ? ` · ${item.lead_score}` : ""}</td>
              <td><Button variant="secondary" onClick={() => setSelected(item)}>Review</Button></td>
            </tr>)}
            {!callbacks.data?.length && <tr><td colSpan={7} className="py-10 text-center text-sm text-slate-400">No callback tasks match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
    </Card>

    <Modal title={`Callback · ${selected?.customer_name || ""}`} open={Boolean(selected)} onClose={() => setSelected(null)}>
      {selected && <form className="space-y-4" onSubmit={save}>
        <div className="rounded-xl bg-slate-50 p-4">
          <div className="flex items-center gap-2 font-bold text-slate-900"><PhoneCall size={16}/>{selected.customer_phone || "No phone number"}</div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{selected.call_summary || "No call summary is available."}</p>
          {selected.source_call_log_id && <a className="mt-2 inline-block text-sm font-semibold text-indigo-600" href={`/calls/${selected.source_call_log_id}`}>Open source call</a>}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label><span className="label">Status</span><select className="field" value={form.status} onChange={event => setForm({...form,status:event.target.value as CallbackStatus})}><option value="pending">Pending</option><option value="assigned">Assigned</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></label>
          <label><span className="label">Owner</span><select className="field" value={form.assigned_user_id} onChange={event => setForm({...form,assigned_user_id:event.target.value})}><option value="">Unassigned</option>{(team.data || []).filter(member => member.is_active).map(member => <option key={member.id} value={member.id}>{member.full_name}</option>)}</select></label>
          <label><span className="label">Requested date</span><input className="field" type="date" value={form.requested_date} onChange={event => setForm({...form,requested_date:event.target.value})}/></label>
          <label><span className="label">Scheduled time</span><input className="field" type="datetime-local" value={form.scheduled_at} onChange={event => setForm({...form,scheduled_at:event.target.value})}/></label>
        </div>
        <label><span className="label">Internal notes</span><textarea className="field min-h-28" maxLength={4000} value={form.notes} onChange={event => setForm({...form,notes:event.target.value})}/></label>
        <p className="flex items-center gap-2 text-xs text-slate-500"><CalendarClock size={14}/>Times are displayed in your browser timezone. Organization timezone: {selected.timezone}.</p>
        <div className="flex gap-3"><Button disabled={update.isPending}>{update.isPending ? "Saving…" : "Save callback"}</Button><Button type="button" variant="secondary" onClick={() => setSelected(null)}>Close</Button></div>
      </form>}
    </Modal>
  </>;
}

