import { Save } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { API_BASE_STORAGE_KEY, getApiBaseUrl } from "../api/client";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import "./Settings.css";

export function Settings() {
  const [apiBase, setApiBase] = useState(getApiBaseUrl());

  function save() {
    localStorage.setItem(API_BASE_STORAGE_KEY, apiBase.replace(/\/$/, ""));
    toast.success("API base URL saved.");
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Settings</h1>
          <p className="text-sm text-slate-500">Configure local dashboard preferences.</p>
        </div>
      </div>
      <section className="settings-grid">
        <Card>
          <h2 className="text-lg font-bold">API connection</h2>
          <label className="mt-4 block">
            <span className="label">Base URL</span>
            <input className="field" value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
          </label>
          <Button className="mt-4" onClick={save}>
            <Save size={16} />
            Save
          </Button>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Billing</h2>
            <span className="coming-soon">Coming soon</span>
          </div>
          <p className="mt-3 text-sm text-slate-500">Plan usage, invoices, and calling credits will appear here.</p>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Team</h2>
            <span className="coming-soon">Coming soon</span>
          </div>
          <p className="mt-3 text-sm text-slate-500">Invite agents, set roles, and manage workspace access.</p>
        </Card>
      </section>
    </>
  );
}
