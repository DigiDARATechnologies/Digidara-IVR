import { Bot, Send, X } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";

type Message={role:"user"|"assistant";text:string};
export function AssistantChat(){
 const [open,setOpen]=useState(false);const [text,setText]=useState("");const [busy,setBusy]=useState(false);const location=useLocation();const end=useRef<HTMLDivElement>(null);
 const [messages,setMessages]=useState<Message[]>(()=>{try{return JSON.parse(sessionStorage.getItem("digidara-assistant-chat")||"[]")}catch{return []}});
 useEffect(()=>{sessionStorage.setItem("digidara-assistant-chat",JSON.stringify(messages));end.current?.scrollIntoView({behavior:"smooth"})},[messages,open]);
 async function send(e:FormEvent){e.preventDefault();const question=text.trim();if(!question||busy)return;setMessages(m=>[...m,{role:"user",text:question}]);setText("");setBusy(true);try{const {data}=await api.post("/assistant/chat",{message:question,page:location.pathname});setMessages(m=>[...m,{role:"assistant",text:data.reply||"No answer was returned."}])}catch(err){setMessages(m=>[...m,{role:"assistant",text:getErrorMessage(err)}])}finally{setBusy(false)}}
 return <div className="assistant-widget">{open&&<section className="assistant-window" aria-label="DigiDara data assistant"><header><span><Bot size={18}/></span><div><b>DigiDara Assistant</b><small>Real dashboard data + knowledge</small></div><button onClick={()=>setOpen(false)} aria-label="Close assistant"><X size={18}/></button></header><div className="assistant-messages">{!messages.length&&<div className="assistant-welcome"><Bot/><b>How can I help?</b><p>Ask about live call metrics, campaigns, courses, voice-agent setup, or this page.</p></div>}{messages.map((m,i)=><p key={i} className={`assistant-message ${m.role}`}>{m.text}</p>)}{busy&&<p className="assistant-typing">Thinking from real data…</p>}<div ref={end}/></div><form onSubmit={send}><input value={text} onChange={e=>setText(e.target.value)} placeholder="Ask about DigiDara…" aria-label="Assistant question"/><button disabled={busy||!text.trim()} aria-label="Send"><Send size={17}/></button></form><footer>No customer personal data is shared.</footer></section>}<button className="assistant-fab" onClick={()=>setOpen(v=>!v)} aria-label="Open DigiDara assistant"><Bot size={22}/><span>Ask DigiDara</span></button></div>
}
