import { CheckCircle2, DatabaseZap, RefreshCw, ShieldCheck, Unplug } from "lucide-react";
import { FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { useCrmConnection, useCrmEvents, useDisableCrmConnection, useRetryCrmEvent, useSaveCrmConnection, useTestCrmConnection } from "../api/crm";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";

function eventTone(status: string): "green" | "amber" | "red" | "gray" {
  if (status === "delivered") return "green";
  if (["dead", "failed"].includes(status)) return "red";
  if (["pending", "processing"].includes(status)) return "amber";
  return "gray";
}

export function CrmIntegration() {
  const connection = useCrmConnection();
  const events = useCrmEvents();
  const save = useSaveCrmConnection();
  const disable = useDisableCrmConnection();
  const retry = useRetryCrmEvent();
  const test = useTestCrmConnection();
  const [form, setForm] = useState({ name: "DigiDARA CRM Webhook", webhook_url: "", signing_secret: "" });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.webhook_url.startsWith("https://") || form.signing_secret.length < 16) {
      toast.error("Enter an HTTPS webhook URL and a signing secret of at least 16 characters.");
      return;
    }
    try {
      await save.mutateAsync({ ...form, is_active: true, field_mapping: {} });
      setForm(current => ({ ...current, webhook_url: "", signing_secret: "" }));
      toast.success("CRM connection saved. Waiting events were queued for delivery.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function disconnect() {
    if (!confirm("Disable CRM delivery and remove the encrypted webhook credential?")) return;
    try {
      await disable.mutateAsync();
      toast.success("CRM delivery disabled. Existing events were preserved.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function testConnection() {
    try {
      const result = await test.mutateAsync();
      toast.success(`CRM accepted the signed test (HTTP ${result.response_status}).`);
    } catch (error) { toast.error(getErrorMessage(error)); }
  }

  if (connection.isLoading || events.isLoading) return <Skeleton className="h-[70vh]" />;
  return <>
    <div className="page-head"><div><h1 className="text-2xl font-extrabold">CRM Integration</h1><p className="text-sm text-slate-500">Reliable, signed delivery of call and callback events to DigiDARA CRM.</p></div></div>
    <section className="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
      <Card>
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="flex gap-3"><span className="rounded-lg bg-indigo-50 p-3 text-indigo-600"><DatabaseZap size={21}/></span><div><h2 className="font-bold text-slate-950">Signed webhook</h2><p className="text-sm text-slate-500">Secrets are encrypted per organization.</p></div></div>
          <Badge tone={connection.data?.configured && connection.data.is_active ? "green" : "gray"}>{connection.data?.configured && connection.data.is_active ? "Connected" : "Not connected"}</Badge>
        </div>
        {connection.data?.configured && <div className="mb-5 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-900"><p className="flex items-center gap-2 font-bold"><CheckCircle2 size={16}/>Active endpoint</p><p className="mt-1">{connection.data.endpoint_host}</p><p className="mt-1 text-xs">The full URL and signing secret are never returned to the browser.</p></div>}
        <form className="space-y-4" onSubmit={submit}>
          <label><span className="label">Connection name</span><input className="field" value={form.name} onChange={event => setForm({...form,name:event.target.value})}/></label>
          <label><span className="label">HTTPS webhook URL</span><input className="field" type="url" placeholder="https://crm.example.com/webhooks/digidara" value={form.webhook_url} onChange={event => setForm({...form,webhook_url:event.target.value})}/></label>
          <label><span className="label">Signing secret</span><input className="field" type="password" autoComplete="new-password" placeholder="At least 16 characters" value={form.signing_secret} onChange={event => setForm({...form,signing_secret:event.target.value})}/></label>
          <p className="flex gap-2 text-xs leading-5 text-slate-500"><ShieldCheck className="mt-0.5 shrink-0" size={15}/>Deliveries include an HMAC-SHA256 signature and idempotency key. Redirects and private-network destinations are blocked.</p>
          <div className="flex flex-wrap gap-3"><Button disabled={save.isPending}>{save.isPending ? "Saving…" : connection.data?.configured ? "Rotate connection" : "Connect CRM"}</Button>{connection.data?.configured && <Button type="button" variant="secondary" onClick={testConnection} disabled={test.isPending}>{test.isPending?"Testing…":"Send test"}</Button>}{connection.data?.configured && <Button type="button" variant="ghost" onClick={disconnect} disabled={disable.isPending}><Unplug size={15}/>Disable</Button>}</div>
          {connection.data?.last_test_status&&<p className="text-xs text-slate-500">Last connection test: {connection.data.last_test_status}{connection.data.last_tested_at?` · ${new Date(connection.data.last_tested_at).toLocaleString()}`:""}</p>}
        </form>
      </Card>
      <Card>
        <div className="mb-5 flex items-center justify-between"><div><h2 className="font-bold text-slate-950">Delivery events</h2><p className="text-sm text-slate-500">Durable outbox state; failed events remain available for manual retry.</p></div><RefreshCw size={18} className={events.isFetching ? "animate-spin text-indigo-600" : "text-slate-400"}/></div>
        <div className="table-wrap"><table className="table"><thead><tr><th>Event</th><th>Status</th><th>Attempts</th><th>Created</th><th>Result</th></tr></thead><tbody>
          {(events.data || []).map(item => <tr key={item.id}><td><p className="font-semibold text-slate-900">{item.event_type.replace(/_/g," ")}</p><p className="text-xs text-slate-500">{item.aggregate_type} #{item.aggregate_id}</p></td><td><Badge tone={eventTone(item.status)}>{item.status.replace(/_/g," ")}</Badge></td><td>{item.attempts}/{item.max_attempts}</td><td>{new Date(item.created_at).toLocaleString()}</td><td>{["dead","failed","waiting_configuration"].includes(item.status) ? <Button variant="secondary" disabled={retry.isPending || !connection.data?.is_active} onClick={async()=>{try{await retry.mutateAsync(item.id);toast.success("CRM event queued.")}catch(error){toast.error(getErrorMessage(error))}}}>Retry</Button> : item.response_status || "—"}{item.last_error && <p className="mt-1 max-w-xs text-xs text-red-600">{item.last_error}</p>}</td></tr>)}
          {!events.data?.length && <tr><td colSpan={5} className="py-10 text-center text-sm text-slate-400">No CRM events have been generated yet.</td></tr>}
        </tbody></table></div>
      </Card>
    </section>
  </>;
}
