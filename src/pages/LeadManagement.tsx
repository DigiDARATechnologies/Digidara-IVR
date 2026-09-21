import { format, parseISO } from "date-fns";
import { Filter, Flame, PhoneCall, Search, Snowflake, Sun } from "lucide-react";
import { useMemo, useState } from "react";
import toast from "react-hot-toast";
import { useCampaigns } from "../api/campaigns";
import { useCallLogs, useStartCall } from "../api/calls";
import { getErrorMessage } from "../api/client";
import { useCustomers } from "../api/customers";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Drawer } from "../components/ui/Drawer";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import { StatCard } from "../components/ui/StatCard";
import type { DerivedLead } from "../utils/leads";
import { buildLeads, tierLabel, tierTone } from "../utils/leads";
import "./LeadManagement.css";

function parsed(value?: string | null): Date | null {
  if (!value) return null;
  const date = parseISO(value.replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function LeadManagement() {
  const customers = useCustomers();
  const campaigns = useCampaigns();
  const calls = useCallLogs(false);
  const startCall = useStartCall();

  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState<string>("");
  const [selected, setSelected] = useState<DerivedLead | null>(null);
  const [callLead, setCallLead] = useState<DerivedLead | null>(null);
  const [campaignId, setCampaignId] = useState("");

  const leads = useMemo(
    () => buildLeads(customers.data || [], calls.data || []),
    [customers.data, calls.data]
  );

  const counts = useMemo(() => {
    const c = { hot: 0, warm: 0, cold: 0, unscored: 0 };
    leads.forEach((l) => c[l.tier]++);
    return c;
  }, [leads]);

  const filtered = useMemo(() => {
    return leads
      .filter((lead) => {
        if (tierFilter && lead.tier !== tierFilter) return false;
        const haystack = [lead.customer.name, lead.customer.email, lead.customer.phone || "", lead.customer.investigated_course || ""]
          .join(" ")
          .toLowerCase();
        if (search && !haystack.includes(search.toLowerCase())) return false;
        return true;
      })
      .sort((a, b) => (b.leadScore ?? -1) - (a.leadScore ?? -1));
  }, [leads, search, tierFilter]);

  async function runCall() {
    if (!callLead || !campaignId) {
      toast.error("Choose a campaign.");
      return;
    }
    try {
      const result = await startCall.mutateAsync({
        customerId: callLead.customer.id,
        campaignId: Number(campaignId),
      });
      toast.success(result.message || "Call started.");
      setCallLead(null);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  if (customers.isLoading || calls.isLoading) return <Skeleton className="h-[70vh]" />;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Lead Management</h1>
          <p className="text-sm text-slate-500">
            Leads are scored automatically from AI call analysis — no manual entry needed.
          </p>
        </div>
      </div>

      <section className="leads-stat-grid">
        <StatCard icon={Flame} label="Hot Leads" value={String(counts.hot)} hint="Score 70+ · ready to close" />
        <StatCard icon={Sun} label="Warm Leads" value={String(counts.warm)} hint="Score 40-69 · needs nurturing" />
        <StatCard icon={Snowflake} label="Cold Leads" value={String(counts.cold)} hint="Score under 40" />
        <StatCard icon={Filter} label="Not Yet Scored" value={String(counts.unscored)} hint="No completed call yet" />
      </section>

      <Card>
        <div className="leads-toolbar">
          <label className="relative w-full md:max-w-sm">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
            <input
              className="field pl-9"
              placeholder="Search leads by name, email, course…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {(["", "hot", "warm", "cold", "unscored"] as const).map((tier) => (
              <button
                key={tier || "all"}
                className={`tier-filter-chip ${tierFilter === tier ? "tier-filter-chip-active" : ""}`}
                onClick={() => setTierFilter(tier)}
              >
                {tier ? tierLabel[tier] : "All"}
              </button>
            ))}
          </div>
        </div>

        <div className="table-wrap leads-table">
          <table className="table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Course Interest</th>
                <th>Lead Score</th>
                <th>Tier</th>
                <th>Calls</th>
                <th>Last Contacted</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-sm text-slate-400">
                    No leads match your filters.
                  </td>
                </tr>
              )}
              {filtered.map((lead) => (
                <tr key={lead.customer.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setSelected(lead)}>
                  <td>
                    <p className="font-bold text-slate-900">{lead.customer.name}</p>
                    <p className="text-xs text-slate-500">{lead.customer.email}</p>
                  </td>
                  <td className="text-slate-600">{lead.customer.investigated_course || "--"}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="lead-score-bar">
                        <div
                          className="lead-score-bar-fill"
                          style={{ width: `${lead.leadScore ?? 0}%` }}
                        />
                      </div>
                      <span className="text-xs font-bold tabular-nums text-slate-600">
                        {lead.leadScore ?? "--"}
                      </span>
                    </div>
                  </td>
                  <td>
                    <Badge tone={tierTone[lead.tier]}>{tierLabel[lead.tier]}</Badge>
                  </td>
                  <td className="text-center font-semibold text-slate-700">{lead.callCount}</td>
                  <td className="whitespace-nowrap text-slate-500">
                    {parsed(lead.lastContacted) ? format(parsed(lead.lastContacted) as Date, "PP") : "Never"}
                  </td>
                  <td>
                    <button
                      className="icon-btn"
                      title="Call now"
                      onClick={(e) => {
                        e.stopPropagation();
                        setCallLead(lead);
                      }}
                    >
                      <PhoneCall size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="space-y-3 md:hidden">
          {filtered.map((lead) => (
            <button
              key={lead.customer.id}
              className="w-full rounded-xl border border-slate-100 bg-white p-4 text-left shadow-sm"
              onClick={() => setSelected(lead)}
            >
              <div className="flex items-center justify-between">
                <p className="font-bold text-slate-900">{lead.customer.name}</p>
                <Badge tone={tierTone[lead.tier]}>{tierLabel[lead.tier]}</Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500">{lead.customer.investigated_course || "--"}</p>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs font-bold text-slate-600">Score: {lead.leadScore ?? "--"}</span>
                <span className="text-xs text-slate-500">{lead.callCount} calls</span>
              </div>
            </button>
          ))}
        </div>
      </Card>

      <Drawer title={selected?.customer.name || "Lead detail"} open={Boolean(selected)} onClose={() => setSelected(null)}>
        {selected && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Badge tone={tierTone[selected.tier]}>{tierLabel[selected.tier]}</Badge>
              <span className="text-sm font-bold text-slate-700">Score: {selected.leadScore ?? "Not scored"}</span>
            </div>
            <Card>
              <p className="label">Contact</p>
              <p className="mt-1 text-sm text-slate-700">{selected.customer.email}</p>
              <p className="text-sm text-slate-700">{selected.customer.phone || "No phone on file"}</p>
            </Card>
            <Card>
              <p className="label">Interested In</p>
              <p className="mt-1 text-sm text-slate-700">
                {selected.customer.investigated_course || "--"}
                {selected.customer.internship_or_course ? ` (${selected.customer.internship_or_course})` : ""}
              </p>
            </Card>
            {selected.latestCall?.summary && (
              <Card>
                <p className="label">Latest Call Summary</p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{selected.latestCall.summary}</p>
              </Card>
            )}
            <Button
              className="w-full"
              onClick={() => {
                setCallLead(selected);
                setSelected(null);
              }}
            >
              <PhoneCall size={16} />
              Call this lead
            </Button>
          </div>
        )}
      </Drawer>

      <Modal title={`Call ${callLead?.customer.name || ""}`} open={Boolean(callLead)} onClose={() => setCallLead(null)}>
        <div className="space-y-4">
          <label>
            <span className="label">Campaign</span>
            <select className="field" value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
              <option value="">Select campaign</option>
              {(campaigns.data || []).map((c) => (
                <option key={c.id} value={c.id}>{c.campaign_name}</option>
              ))}
            </select>
          </label>
          <Button onClick={runCall} disabled={startCall.isPending}>
            <PhoneCall size={16} />
            Start call
          </Button>
        </div>
      </Modal>
    </>
  );
}
