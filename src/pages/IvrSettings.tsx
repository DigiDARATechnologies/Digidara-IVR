import { FormEvent, useEffect, useState } from "react";
import { ListTree, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { useCampaigns } from "../api/campaigns";
import { useTransferDestinations } from "../api/transfers";
import { getErrorMessage } from "../api/client";
import { useIvrSettings, useSaveIvrSettings } from "../api/ivr";
import type { IvrOption, IvrSettings } from "../types";

const blank: IvrSettings = { is_active: false, timeout_seconds: 7, prompt_english: "", prompt_tamil: "", options: [] };

export function IvrSettings() {
  const settings = useIvrSettings();
  const campaigns = useCampaigns();
  const destinations = useTransferDestinations(true);
  const save = useSaveIvrSettings();
  const [form, setForm] = useState<IvrSettings>(blank);
  useEffect(() => { if (settings.data) setForm(settings.data); }, [settings.data]);

  function setOption(index: number, patch: Partial<IvrOption>) {
    setForm({...form, options: form.options.map((x,i)=>i===index?{...x,...patch}:x)});
  }

  function addOption() {
    const used = new Set(form.options.map(item => item.digit));
    const digit = ["1","2","3","4","5","6","7","8","9"].find(item => !used.has(item));
    if (!digit) return toast.error("An IVR can have at most nine options.");
    const campaign = campaigns.data?.[0];
    if (!campaign) return toast.error("Create a campaign before adding an IVR option.");
    setForm({...form, options: [...form.options, {digit, label: "", campaign_id: campaign.id, destination_id: null, is_active: true, sort_order: form.options.length + 1}]});
  }

  function setRouteType(index: number, routeType: "ai" | "human") {
    if (routeType === "human") {
      const destination = destinations.data?.[0];
      if (!destination) return toast.error("Add an active transfer destination first — see Human Transfer.");
      setOption(index, { destination_id: destination.id, campaign_id: null });
    } else {
      const campaign = campaigns.data?.[0];
      if (!campaign) return toast.error("Create a campaign before routing to AI.");
      setOption(index, { campaign_id: campaign.id, destination_id: null });
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await save.mutateAsync(form);
      toast.success(form.is_active ? "IVR enabled for new calls." : "IVR saved and disabled.");
    } catch (error) { toast.error(getErrorMessage(error)); }
  }

  if (settings.isLoading || campaigns.isLoading || destinations.isLoading) return <p>Loading IVR settings…</p>;
  return <>
    <div className="page-heading"><div><h1>IVR Menu</h1><p>The AI voice assistant itself greets the caller and asks this question in conversation — there is no separate pre-recorded menu. Once the caller answers, it routes into an AI campaign or straight to a human; a human-routed option ends the AI's involvement entirely.</p></div></div>
    <form className="space-y-5" onSubmit={submit}>
      <section className="panel form-grid">
        <h2><ListTree size={20}/> Menu controls</h2>
        <label className="flex items-center gap-3"><input type="checkbox" checked={form.is_active} onChange={e=>setForm({...form,is_active:e.target.checked})}/><span>Enable this IVR for this organization</span></label>
        <label>English question (optional)<textarea maxLength={500} value={form.prompt_english} onChange={e=>setForm({...form,prompt_english:e.target.value})} placeholder="What do you need help with today — Business, Support, or Education?"/></label>
        <label>Tamil question (optional)<textarea maxLength={500} value={form.prompt_tamil} onChange={e=>setForm({...form,prompt_tamil:e.target.value})} placeholder="இன்னைக்கு உங்களுக்கு என்ன உதவி வேணும் — Business, Support, அல்லது Education?"/></label>
        <p className="text-sm text-slate-500">This is the exact question the AI asks out loud right after greeting the caller. When blank, a question is generated from the option labels below. Never put customer data or credentials here.</p>
      </section>
      <section className="panel">
        <div className="mb-4 flex items-center justify-between"><div><h2>Menu options</h2><p className="text-sm text-slate-500">Each digit routes to either an AI campaign or a human transfer destination — never both.</p></div><button type="button" className="accent-btn" onClick={addOption}><Plus size={16}/>Add option</button></div>
        {!campaigns.isLoading && !campaigns.data?.length && <p className="mb-3 text-sm text-slate-500"><Link to="/campaigns" className="font-semibold text-indigo-600 hover:underline">Create a campaign</Link> first — an AI-routed option needs one to route into.</p>}
        {!destinations.isLoading && !destinations.data?.length && <p className="mb-3 text-sm text-slate-500"><Link to="/transfers" className="font-semibold text-indigo-600 hover:underline">Add a transfer destination</Link> if you want an option to ring a human directly.</p>}
        <div className="space-y-3">{form.options.map((item,index)=>{
          const routeType: "ai" | "human" = item.destination_id ? "human" : "ai";
          return <div className="grid gap-3 md:grid-cols-[60px_1fr_120px_1fr_80px_42px]" key={item.digit}>
            <label>Digit<select value={item.digit} onChange={e=>setOption(index,{digit:e.target.value})}>{["1","2","3","4","5","6","7","8","9"].map(d=><option key={d} value={d}>{d}</option>)}</select></label>
            <label>Caller label<input required value={item.label} onChange={e=>setOption(index,{label:e.target.value})} placeholder="Sales"/></label>
            <label>Route to<select value={routeType} onChange={e=>setRouteType(index, e.target.value as "ai" | "human")}>
              <option value="ai">AI campaign</option>
              <option value="human">Human (direct)</option>
            </select></label>
            {routeType === "human"
              ? <label>Destination<select value={item.destination_id||0} onChange={e=>setOption(index,{destination_id:Number(e.target.value)})}>
                  {destinations.data?.map(d=><option key={d.id} value={d.id}>{d.name} · {d.phone_e164}</option>)}
                </select></label>
              : <label>AI campaign<select value={item.campaign_id||0} onChange={e=>setOption(index,{campaign_id:Number(e.target.value)})}>{campaigns.data?.map(c=><option key={c.id} value={c.id}>{c.campaign_name}</option>)}</select></label>}
            <label className="flex items-center gap-2 pt-6"><input type="checkbox" checked={item.is_active} onChange={e=>setOption(index,{is_active:e.target.checked})}/>Active</label>
            <button className="mt-6 text-red-600" type="button" aria-label="Remove option" onClick={()=>setForm({...form,options:form.options.filter((_,i)=>i!==index)})}><Trash2 size={18}/></button>
          </div>;
        })}</div>
        {!form.options.length&&<p className="py-8 text-center text-sm text-slate-500">No options yet. The IVR remains disabled until you add an active option.</p>}
      </section>
      <button className="accent-btn" disabled={save.isPending}>{save.isPending?"Saving…":"Save IVR configuration"}</button>
    </form>
  </>;
}
