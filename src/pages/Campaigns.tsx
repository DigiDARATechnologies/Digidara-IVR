import { Edit3, Megaphone, MessageSquareText, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";
import { useCampaigns, useDeleteCampaign, useSaveCampaign } from "../api/campaigns";
import { getErrorMessage } from "../api/client";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import type { Campaign, CampaignPayload } from "../types";
import { CampaignEditor } from "./CampaignEditor";
import "./Campaigns.css";

const emptyCampaign: CampaignPayload = {
  campaign_name: "",
  objective: "",
  ai_prompt: ""
};

export function Campaigns() {
  const navigate = useNavigate();
  const campaigns = useCampaigns();
  const saveCampaign = useSaveCampaign();
  const deleteCampaign = useDeleteCampaign();
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CampaignPayload>(emptyCampaign);
  const [lastSavedId, setLastSavedId] = useState<number | null>(null);

  function startEdit(campaign?: Campaign) {
    setEditing(campaign || null);
    setForm(
      campaign
        ? {
            campaign_name: campaign.campaign_name,
            objective: campaign.objective,
            ai_prompt: campaign.ai_prompt
          }
        : emptyCampaign
    );
    setOpen(true);
  }

  async function save() {
    if (!form.campaign_name.trim() || !form.objective.trim() || !form.ai_prompt.trim()) {
      toast.error("All campaign fields are required.");
      return;
    }
    try {
      const result = await saveCampaign.mutateAsync({ id: editing?.id, payload: form });
      toast.success(
        editing
          ? "Campaign updated — the new prompt will be used on the very next call."
          : "Campaign created."
      );
      setLastSavedId(result.id);
      setOpen(false);
      setTimeout(() => setLastSavedId(null), 4000);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function remove(campaign: Campaign) {
    if (!confirm(`Delete ${campaign.campaign_name}?`)) return;
    try {
      await deleteCampaign.mutateAsync(campaign.id);
      toast.success("Campaign deleted.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  if (campaigns.isLoading) return <Skeleton className="h-[70vh]" />;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Campaigns</h1>
          <p className="text-sm text-slate-500">Create and tune voice assistant prompts.</p>
        </div>
        <Button onClick={() => navigate("/campaigns/new")}>
          <Plus size={16} />
          New campaign
        </Button>
      </div>

      <section className="campaign-grid">
        {(campaigns.data || []).map((campaign) => (
          <Card
            key={campaign.id}
            className={`transition hover:shadow-md ${lastSavedId === campaign.id ? "campaign-just-saved" : ""}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="rounded-lg bg-indigo-50 p-3 text-indigo-600">
                <Megaphone size={20} />
              </div>
              <div className="flex gap-2">
                <button className="icon-btn" title="Test in Playground" onClick={() => navigate(`/playground?campaign=${campaign.id}`)}>
                  <MessageSquareText size={16} />
                </button>
                <button className="icon-btn" title="Edit" onClick={() => navigate(`/campaigns/${campaign.id}/edit`)}>
                  <Edit3 size={16} />
                </button>
                <button className="icon-btn" title="Delete" onClick={() => remove(campaign)}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            <h2 className="mt-4 text-lg font-bold">{campaign.campaign_name}</h2>
            <p className="mt-2 line-clamp-3 text-sm text-slate-500">{campaign.objective}</p>
            <details className="campaign-prompt-preview">
              <summary className="cursor-pointer text-xs font-bold uppercase tracking-normal text-slate-400 hover:text-indigo-600">
                {campaign.ai_prompt.length} prompt chars · view current prompt ▸
              </summary>
              <p className="mt-2 whitespace-pre-wrap text-xs text-slate-500">{campaign.ai_prompt}</p>
            </details>
            {lastSavedId === campaign.id && (
              <p className="mt-3 text-xs font-bold text-emerald-600">✓ Just saved — this is the live prompt now.</p>
            )}
          </Card>
        ))}
        {!campaigns.data?.length && (
          <Card className="md:col-span-2 xl:col-span-3">
            <p className="text-sm text-slate-500">No campaigns yet.</p>
          </Card>
        )}
      </section>

      <Modal title={editing ? "Edit campaign" : "New campaign"} open={open} onClose={() => setOpen(false)}>
        <CampaignEditor value={form} onChange={setForm} onSubmit={save} saving={saveCampaign.isPending} />
      </Modal>
    </>
  );
}
