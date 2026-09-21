import { Mic, Send, Volume2 } from "lucide-react";
import { FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { getErrorMessage } from "../api/client";
import { queryFacilityAgent, seedFacilityDemo, type FacilityAgentResponse } from "../api/facility";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

type Message = { role: "operator" | "agent"; text: string; result?: FacilityAgentResponse };

export function FacilityConsole() {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = message.trim();
    if (!text || loading) return;
    setMessages((current) => [...current, { role: "operator", text }]);
    setMessage(""); setLoading(true);
    try {
      const result = await queryFacilityAgent(text);
      setMessages((current) => [...current, { role: "agent", text: result.reply, result }]);
      window.speechSynthesis?.speak(new SpeechSynthesisUtterance(result.reply));
    } catch (error) { toast.error(getErrorMessage(error)); }
    finally { setLoading(false); }
  }

  function startListening() {
    const Recognition = (window as unknown as { SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any }).SpeechRecognition
      || (window as unknown as { webkitSpeechRecognition?: new () => any }).webkitSpeechRecognition;
    if (!Recognition) { toast.error("Speech recognition is not supported in this browser. Type your request instead."); return; }
    const recognition = new Recognition(); recognition.lang = "en-IN"; recognition.interimResults = false;
    recognition.onresult = (event: any) => setMessage(event.results[0][0].transcript);
    recognition.onerror = () => toast.error("Voice input could not be captured. Please try again."); recognition.start();
  }

  return <>
    <div className="page-heading"><div><h1>Facility Voice Console</h1><p>Grounded, confirmation-safe operations assistant.</p></div><Button onClick={async () => { await seedFacilityDemo(); toast.success("Building A demo data is ready."); }}>Load demo</Button></div>
    <section className="two-col"><Card><h2>Conversation</h2><div className="space-y-3" style={{ minHeight: 360 }}>
      {!messages.length && <p className="text-sm text-slate-500">Try: “Building A is too hot. Investigate the HVAC system.”</p>}
      {messages.map((item, index) => <div key={index} className={item.role === "operator" ? "chat-bubble-user" : "chat-bubble-ai"}><p>{item.text}</p>{item.result?.requires_confirmation && <p className="mt-2 text-xs font-bold text-amber-600">Confirmation is required before a maintenance request can be created.</p>}{item.result?.citations.map((citation) => <p key={citation.source_id} className="mt-2 text-xs text-slate-500">Source: {citation.title} (rev {citation.revision})</p>)}</div>)}
    </div><form className="mt-4 flex gap-2" onSubmit={submit}><input className="field" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask about HVAC, alerts, or a procedure"/><Button disabled={loading}><Send size={16}/>Send</Button><button type="button" className="soft-btn" onClick={startListening} aria-label="Speak request"><Mic size={16}/></button></form></Card>
    <Card><h2>Safety controls</h2><div className="flow-list"><div><b>1</b>Retrieve MCP evidence</div><div><b>2</b>Ground procedure answers with citations</div><div><b>3</b>Ask before maintenance actions</div></div><p className="mt-5 text-xs text-slate-500"><Volume2 size={14} className="mr-1 inline"/>Responses are spoken by the browser when available. Production phone calls remain on the existing Plivo/OpenAI Realtime path.</p></Card></section>
  </>;
}
