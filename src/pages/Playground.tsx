import { Send } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { sendChatMessage } from "../api/chat";
import { useCampaigns } from "../api/campaigns";
import { getErrorMessage } from "../api/client";
import { useCustomers } from "../api/customers";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import "./Playground.css";

interface Message {
  role: "user" | "assistant";
  text: string;
  latency?: number;
}

export function Playground() {
  const [searchParams] = useSearchParams();
  const campaigns = useCampaigns();
  const customers = useCustomers();
  const [campaignId, setCampaignId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fromQuery = searchParams.get("campaign");
    if (fromQuery) setCampaignId(fromQuery);
  }, [searchParams]);

  const selectedCampaign = (campaigns.data || []).find((c) => String(c.id) === campaignId);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaignId || !message.trim()) {
      toast.error("Choose a campaign and enter a message.");
      return;
    }
    const userText = message.trim();
    setMessages((current) => [...current, { role: "user", text: userText }]);
    setMessage("");
    setLoading(true);
    const start = performance.now();
    try {
      const response = await sendChatMessage({
        campaignId: Number(campaignId),
        customerId: customerId ? Number(customerId) : undefined,
        message: userText
      });
      const latency = Math.round(performance.now() - start);
      setMessages((current) => [
        ...current,
        { role: "assistant", text: response.reply || response.error || "No reply returned.", latency }
      ]);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Playground</h1>
          <p className="text-sm text-slate-500">Test campaign prompts before live calls.</p>
        </div>
      </div>
      <section className="playground-grid">
        <Card>
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
            <label>
              <span className="label">Customer context</span>
              <select className="field" value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
                <option value="">No customer</option>
                {(customers.data || []).map((customer) => (
                  <option key={customer.id} value={customer.id}>{customer.name}</option>
                ))}
              </select>
            </label>
            {selectedCampaign && (
              <details className="playground-prompt-preview">
                <summary className="cursor-pointer text-xs font-bold uppercase tracking-normal text-slate-400 hover:text-indigo-600">
                  View active prompt ▸
                </summary>
                <p className="mt-2 whitespace-pre-wrap text-xs text-slate-500">{selectedCampaign.ai_prompt}</p>
              </details>
            )}
            <p className="text-xs text-slate-400">
              This uses the exact same campaign prompt as live phone calls — test here before calling real customers.
            </p>
          </div>
        </Card>
        <div className="chat-window">
          <div className="flex-1 space-y-3 overflow-auto p-4">
            {messages.map((item, index) => (
              <div key={`${item.role}-${index}`} className={item.role === "user" ? "chat-bubble-user" : "chat-bubble-ai"}>
                <p>{item.text}</p>
                {item.latency !== undefined && <p className="mt-2 text-xs font-bold text-slate-500">{item.latency} ms</p>}
              </div>
            ))}
            {!messages.length && <p className="text-sm text-slate-500">Start a test conversation.</p>}
          </div>
          <form className="flex gap-3 border-t border-slate-100 p-4" onSubmit={submit}>
            <input className="field" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Type a customer message" />
            <Button disabled={loading}>
              <Send size={16} />
              Send
            </Button>
          </form>
        </div>
      </section>
    </>
  );
}
