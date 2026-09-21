import { addDays, format, isSameDay, parseISO, startOfDay, subDays } from "date-fns";
import { AlertTriangle, Clock3, Flame, Megaphone, PhoneCall, Radio } from "lucide-react";
import { useMemo, useState } from "react";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";
import { useCampaigns } from "../api/campaigns";
import { useCallLogs, useStartCall } from "../api/calls";
import { getErrorMessage } from "../api/client";
import { useCustomers } from "../api/customers";
import { CallsLineChart } from "../components/charts/CallsLineChart";
import { OutcomeDonutChart } from "../components/charts/OutcomeDonutChart";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { LiveDuration } from "../components/ui/LiveDuration";
import { Skeleton } from "../components/ui/Skeleton";
import { StatCard } from "../components/ui/StatCard";
import { formatDuration } from "../utils/formatDuration";
import { buildLeads } from "../utils/leads";
import { isLiveStatus, normalizedStatus, statusTone } from "../utils/statusBadge";
import "./Dashboard.css";

function parseDate(value?: string | null): Date | null {
  if (!value) return null;
  const parsed = parseISO(value.replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function Dashboard() {
  const navigate = useNavigate();
  const customers = useCustomers();
  const campaigns = useCampaigns();
  const initialCalls = useCallLogs(false);
  const hasLive = (initialCalls.data || []).some((log) => isLiveStatus(log.status, log.call_status, log.created_at));
  const calls = useCallLogs(hasLive ? 5000 : false);
  const startCall = useStartCall();
  const [customerId, setCustomerId] = useState("");
  const [campaignId, setCampaignId] = useState("");

  const logs = calls.data || initialCalls.data || [];
  const today = startOfDay(new Date());

  const completedDurations = logs
    .map((l) => l.duration)
    .filter((d): d is number => typeof d === "number" && d > 0);
  const averageDuration = completedDurations.length
    ? Math.round(completedDurations.reduce((s, v) => s + v, 0) / completedDurations.length)
    : null;

  const callsToday = logs.filter((log) => {
    const created = parseDate(log.created_at);
    return created ? isSameDay(created, today) : false;
  }).length;

  const leads = useMemo(() => buildLeads(customers.data || [], logs), [customers.data, logs]);
  const hotLeads = leads.filter((l) => l.tier === "hot").length;

  const liveCalls = logs.filter((log) => isLiveStatus(log.status, log.call_status, log.created_at));
  const abnormalCalls = logs.filter((log) => log.is_abnormal);

  const customerMap = useMemo(() => {
    const map = new Map<number, string>();
    (customers.data || []).forEach((c) => map.set(c.id, c.name));
    return map;
  }, [customers.data]);

  const trendData = useMemo(
    () =>
      Array.from({ length: 14 }, (_, index) => {
        const date = addDays(subDays(today, 13), index);
        return {
          day: format(date, "MMM d"),
          calls: logs.filter((log) => {
            const created = parseDate(log.created_at);
            return created ? isSameDay(created, date) : false;
          }).length,
        };
      }),
    [logs, today]
  );

  const outcomeData = useMemo(() => {
    const grouped = new Map<string, number>();
    logs.forEach((log) => {
      const key = normalizedStatus(log.status, log.call_status);
      grouped.set(key, (grouped.get(key) || 0) + 1);
    });
    return Array.from(grouped.entries()).map(([name, value]) => ({ name, value }));
  }, [logs]);

  async function handleQuickCall() {
    if (!customerId || !campaignId) {
      toast.error("Choose a customer and campaign.");
      return;
    }
    try {
      const result = await startCall.mutateAsync({
        customerId: Number(customerId),
        campaignId: Number(campaignId),
      });
      if (result.status === "simulated") {
        toast.error(`Simulation mode: ${result.message}`, { duration: 6000 });
      } else if (result.status === "failed") {
        toast.error(`Call failed: ${result.message}`, { duration: 6000 });
      } else {
        toast.success(result.message || "Call initiated!");
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  if (customers.isLoading || campaigns.isLoading || initialCalls.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40" />
        <div className="dashboard-grid">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Hero banner */}
      <section className="dashboard-hero">
        <p className="dashboard-hero-eyebrow">DigiDara AI Voice Assistant</p>
        <h1 className="dashboard-hero-title">Calling Operations Dashboard</h1>
        <p className="dashboard-hero-sub">
          Monitor live activity, understand call outcomes, and launch customer calls — all in one workspace.
        </p>
        {liveCalls.length > 0 && (
          <div className="dashboard-live-bar">
            <Radio size={14} className="animate-pulse text-emerald-400" />
            <span>{liveCalls.length} call{liveCalls.length > 1 ? "s" : ""} in progress</span>
            {liveCalls[0] && (
              <span className="font-mono">
                <LiveDuration createdAt={liveCalls[0].created_at} />
              </span>
            )}
          </div>
        )}
      </section>

      {/* Stat cards */}
      <section className="dashboard-grid">
        <StatCard icon={PhoneCall} label="Calls Today" value={String(callsToday)} hint="From call logs" />
        <StatCard
          icon={Clock3}
          label="Avg Duration"
          value={formatDuration(averageDuration)}
          hint="Completed calls"
        />
        <StatCard
          icon={Megaphone}
          label="Active Campaigns"
          value={String(campaigns.data?.length || 0)}
          hint="Configured prompts"
        />
        <StatCard
          icon={Flame}
          label="Hot Leads"
          value={String(hotLeads)}
          hint="Click to view all leads →"
          onClick={() => navigate("/leads")}
        />
        <StatCard
          icon={AlertTriangle}
          label="Call Alerts"
          value={String(abnormalCalls.length)}
          hint="Cost or conversation guardrails →"
          onClick={() => navigate("/calls?alerts=1")}
        />
      </section>

      {/* Charts */}
      <section className="dashboard-charts">
        <Card>
          <h2 className="mb-4 text-lg font-bold text-slate-900">Calls per day (14 days)</h2>
          <CallsLineChart data={trendData} />
        </Card>
        <Card>
          <h2 className="mb-4 text-lg font-bold text-slate-900">Call outcomes</h2>
          <OutcomeDonutChart data={outcomeData} />
          <div className="mt-3 flex flex-wrap gap-2">
            {outcomeData.slice(0, 6).map((item) => (
              <Badge key={item.name} tone={statusTone(item.name)}>
                {item.name}
              </Badge>
            ))}
          </div>
        </Card>
      </section>

      {/* Recent calls + Quick call */}
      <section className="quick-call">
        <Card>
          <h2 className="mb-4 text-lg font-bold text-slate-900">Recent calls</h2>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Health</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {logs.slice(0, 7).map((log) => {
                  const live = isLiveStatus(log.status, log.call_status, log.created_at);
                  return (
                    <tr key={log.id}>
                      <td className="font-semibold text-slate-900">
                        {log.customer_id ? (customerMap.get(log.customer_id) || `#${log.customer_id}`) : "--"}
                      </td>
                      <td>
                        <Badge tone={statusTone(log.status, log.call_status)}>
                          {normalizedStatus(log.status, log.call_status)}
                        </Badge>
                      </td>
                      <td className="font-semibold tabular-nums text-slate-700">
                        {live ? (
                          <span className="flex items-center gap-1.5 text-amber-700">
                            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
                            <LiveDuration createdAt={log.created_at} />
                          </span>
                        ) : (
                          formatDuration(log.duration)
                        )}
                      </td>
                      <td>
                        <Badge tone={log.is_abnormal ? "red" : "green"}>
                          {log.is_abnormal ? "Review" : "Normal"}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap text-slate-500">
                        {parseDate(log.created_at)
                          ? format(parseDate(log.created_at) as Date, "PP")
                          : "--"}
                      </td>
                    </tr>
                  );
                })}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-sm text-slate-400">
                      No calls yet. Start one below!
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-bold text-slate-900">Quick call</h2>
          <p className="mt-1 text-sm text-slate-500">Launch a call directly from here.</p>
          <div className="mt-5 space-y-4">
            <label>
              <span className="label">Customer</span>
              <select
                className="field"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
              >
                <option value="">Select customer</option>
                {(customers.data || []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.phone ? `· ${c.phone}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="label">Campaign</span>
              <select
                className="field"
                value={campaignId}
                onChange={(e) => setCampaignId(e.target.value)}
              >
                <option value="">Select campaign</option>
                {(campaigns.data || []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.campaign_name}
                  </option>
                ))}
              </select>
            </label>
            <Button
              className="w-full"
              onClick={handleQuickCall}
              disabled={startCall.isPending || !customerId || !campaignId}
            >
              <PhoneCall size={16} />
              {startCall.isPending ? "Dialling…" : "Start call"}
            </Button>
          </div>
        </Card>
      </section>
    </>
  );
}
