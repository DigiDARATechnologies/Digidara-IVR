import { Edit3, History, PhoneCall, Plus, Search, Trash2 } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { useCampaigns } from "../api/campaigns";
import { useCallLogs, useStartCall } from "../api/calls";
import { getErrorMessage } from "../api/client";
import { useCustomers, useDeleteCustomer, useSaveCustomer } from "../api/customers";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Drawer } from "../components/ui/Drawer";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import type { Customer, CustomerPayload } from "../types";
import { formatDuration } from "../utils/formatDuration";
import { buildLeads, tierLabel, tierTone } from "../utils/leads";
import { normalizedStatus, statusTone } from "../utils/statusBadge";
import "./Customers.css";

const emptyCustomer: CustomerPayload = {
  name: "",
  email: "",
  phone: "",
  language: "english"
};

export function Customers() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const customers = useCustomers();
  const campaigns = useCampaigns();
  const calls = useCallLogs(false);
  const saveCustomer = useSaveCustomer();
  const deleteCustomer = useDeleteCustomer();
  const startCall = useStartCall();
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [editing, setEditing] = useState<Customer | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<CustomerPayload>(emptyCustomer);
  const [callCustomer, setCallCustomer] = useState<Customer | null>(null);
  const [historyCustomer, setHistoryCustomer] = useState<Customer | null>(null);
  const [campaignId, setCampaignId] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 8;

  const filtered = useMemo(() => {
    const term = search.toLowerCase();
    return (customers.data || []).filter((customer) =>
      [customer.name, customer.email, customer.phone || "", customer.language || ""]
        .join(" ")
        .toLowerCase()
        .includes(term)
    );
  }, [customers.data, search]);

  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const history = (calls.data || []).filter((log) => log.customer_id === historyCustomer?.id);

  const leads = useMemo(
    () => buildLeads(customers.data || [], calls.data || []),
    [customers.data, calls.data]
  );
  const leadByCustomerId = useMemo(() => {
    const map = new Map<number, (typeof leads)[number]>();
    leads.forEach((l) => map.set(l.customer.id, l));
    return map;
  }, [leads]);

  function openForm(customer?: Customer) {
    setEditing(customer || null);
    setForm(
      customer
        ? {
            name: customer.name,
            email: customer.email,
            phone: customer.phone || "",
            language: customer.language || "english"
          }
        : emptyCustomer
    );
    setFormOpen(true);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.name.trim() || !form.email.includes("@")) {
      toast.error("Name and valid email are required.");
      return;
    }
    try {
      await saveCustomer.mutateAsync({ id: editing?.id, payload: form });
      toast.success(editing ? "Customer updated." : "Customer added.");
      setEditing(null);
      setFormOpen(false);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function runCall() {
    if (!callCustomer || !campaignId) {
      toast.error("Choose a campaign.");
      return;
    }
    try {
      const result = await startCall.mutateAsync({
        customerId: callCustomer.id,
        campaignId: Number(campaignId)
      });
      if (result.status === "simulated") {
        toast.error(`Simulation mode: ${result.message}`, { duration: 6000 });
      } else if (result.status === "failed") {
        toast.error(`Call failed: ${result.message}`, { duration: 6000 });
      } else {
        toast.success(result.message || "Call initiated!");
      }
      setCallCustomer(null);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function removeCustomer(customer: Customer) {
    if (!confirm(`Delete ${customer.name}?`)) return;
    try {
      await deleteCustomer.mutateAsync(customer.id);
      toast.success("Customer deleted.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  if (customers.isLoading) return <Skeleton className="h-[70vh]" />;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Customers</h1>
          <p className="text-sm text-slate-500">Manage leads and launch campaign calls.</p>
        </div>
        <Button onClick={() => openForm()}>
          <Plus size={16} />
          Add customer
        </Button>
      </div>

      <Card>
        <div className="customers-toolbar">
          <label className="relative w-full md:max-w-sm">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
            <input className="field pl-10" placeholder="Search customers" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <p className="text-sm font-semibold text-slate-500">{filtered.length} customers</p>
        </div>

        <div className="customers-table table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Language</th>
                <th>Lead</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((customer) => (
                <tr key={customer.id}>
                  <td>
                    <p className="font-bold text-slate-900">{customer.name}</p>
                    <p className="text-xs text-slate-500">{customer.email}</p>
                  </td>
                  <td>{customer.phone || "--"}</td>
                  <td>{customer.language || "--"}</td>
                  <td>
                    {leadByCustomerId.get(customer.id) && (
                      <Badge tone={tierTone[leadByCustomerId.get(customer.id)!.tier]}>
                        {tierLabel[leadByCustomerId.get(customer.id)!.tier]}
                      </Badge>
                    )}
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button className="icon-btn" title="Call now" onClick={() => setCallCustomer(customer)}>
                        <PhoneCall size={16} />
                      </button>
                      <button className="icon-btn" title="Customer 360" onClick={() => navigate(`/customers/${customer.id}`)}>
                        <History size={16} />
                      </button>
                      <button className="icon-btn" title="Edit" onClick={() => openForm(customer)}>
                        <Edit3 size={16} />
                      </button>
                      <button className="icon-btn" title="Delete" onClick={() => removeCustomer(customer)}>
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="space-y-3 md:hidden">
          {paged.map((customer) => (
            <article className="customer-mobile-card" key={customer.id}>
              <p className="font-bold">{customer.name}</p>
              <p className="text-sm text-slate-500">{customer.email}</p>
              <p className="mt-2 text-sm">{customer.phone || "--"} · {customer.language || "--"}</p>
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" onClick={() => setCallCustomer(customer)}>
                  <PhoneCall size={15} />
                  Call
                </Button>
                <Button variant="ghost" onClick={() => openForm(customer)}>
                  <Edit3 size={15} />
                  Edit
                </Button>
              </div>
            </article>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between">
          <Button variant="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span className="text-sm font-semibold text-slate-500">Page {page} of {pages}</span>
          <Button variant="secondary" disabled={page === pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      </Card>

      <Modal title={editing ? "Edit customer" : "Add customer"} open={formOpen} onClose={() => setFormOpen(false)}>
        <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
          {(["name", "email", "phone", "language"] as const).map((field) => (
            <label key={field}>
              <span className="label">{field.replace(/_/g, " ")}</span>
              <input className="field" value={form[field] || ""} onChange={(event) => setForm({ ...form, [field]: event.target.value })} />
            </label>
          ))}
          <div className="flex gap-3 md:col-span-2">
            <Button disabled={saveCustomer.isPending}>Save</Button>
            <Button type="button" variant="secondary" onClick={() => setFormOpen(false)}>Cancel</Button>
          </div>
        </form>
      </Modal>

      <Modal title={`Call ${callCustomer?.name || ""}`} open={Boolean(callCustomer)} onClose={() => setCallCustomer(null)}>
        <div className="space-y-4">
          <label>
            <span className="label">Campaign</span>
            <select className="field" value={campaignId} onChange={(event) => setCampaignId(event.target.value)}>
              <option value="">Select campaign</option>
              {(campaigns.data || []).map((campaign) => (
                <option key={campaign.id} value={campaign.id}>{campaign.campaign_name}</option>
              ))}
            </select>
          </label>
          <Button onClick={runCall} disabled={startCall.isPending}>
            <PhoneCall size={16} />
            Start call
          </Button>
        </div>
      </Modal>

      <Drawer title={`${historyCustomer?.name || "Customer"} — Call History`} open={Boolean(historyCustomer)} onClose={() => setHistoryCustomer(null)}>
        <div className="space-y-4">
          {!history.length && (
            <p className="py-8 text-center text-sm text-slate-400">No call history yet for this customer.</p>
          )}
          {history.map((log) => (
            <div key={log.id} className="rounded-xl border border-slate-100 bg-white shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-50 px-4 py-3">
                <Badge tone={statusTone(log.status, log.call_status)}>
                  {normalizedStatus(log.status, log.call_status)}
                </Badge>
                <span className="text-sm font-bold tabular-nums text-slate-700">
                  {formatDuration(log.duration)}
                </span>
              </div>
              {log.summary && (
                <div className="px-4 py-3">
                  <p className="label">AI Summary</p>
                  <p className="mt-1 text-sm leading-relaxed text-slate-700">{log.summary}</p>
                </div>
              )}
              {log.transcript && (
                <details className="px-4 pb-3">
                  <summary className="label cursor-pointer py-2 hover:text-indigo-700">
                    Full transcript ▸
                  </summary>
                  <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-600">
                    {log.transcript}
                  </p>
                </details>
              )}
              {!log.summary && !log.transcript && (
                <p className="px-4 py-3 text-sm text-slate-400">No transcript or summary recorded.</p>
              )}
            </div>
          ))}
        </div>
      </Drawer>
    </>
  );
}
