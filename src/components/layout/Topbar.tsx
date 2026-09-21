import { Bell, LogOut, Menu, Moon, Radio, Search, Sun } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { getApiBaseUrl } from "../../api/client";
import { useEffect, useState } from "react";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const navigate = useNavigate();
  const [dark,setDark]=useState(()=>localStorage.getItem("digidara-theme")==="dark");
  const [search,setSearch]=useState("");
  const user=(()=>{try{return JSON.parse(localStorage.getItem("digidara-user")||"{}") as {full_name?:string;role_code?:string;workspace_slug?:string}}catch{return {}}})();
  const displayName=user.full_name||"Administrator";const initials=displayName.split(/\s+/).map(x=>x[0]).slice(0,2).join("").toUpperCase();
  useEffect(()=>{document.documentElement.dataset.theme=dark?"dark":"light";localStorage.setItem("digidara-theme",dark?"dark":"light")},[dark]);

  function logout() {
    localStorage.removeItem("digidara-token");
    localStorage.removeItem("digidara-user");
    navigate("/login");
  }
  function runSearch(event: React.FormEvent) {
    event.preventDefault();
    const q=search.trim();
    if(!q) return;
    if(/call|sid|phone/i.test(q)) navigate(`/calls?search=${encodeURIComponent(q)}`);
    else if(/campaign/i.test(q)) navigate(`/campaigns?search=${encodeURIComponent(q)}`);
    else navigate(`/customers?search=${encodeURIComponent(q)}`);
  }

  return (
    <header className="topbar">
      <button className="icon-btn md:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu size={19} />
      </button>
      <form className="top-search" onSubmit={runSearch}><Search size={17}/><input aria-label="Global search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search customers, calls, campaigns..."/></form>
      <div className="top-actions"><span className="api-health"><Radio size={14}/> Live</span><span className="language-btn">English <b>EN</b> தமிழ் <b>TA</b></span><button className="icon-btn" onClick={()=>setDark(v=>!v)} aria-label="Toggle complete light or dark theme">{dark?<Sun size={18}/>:<Moon size={18}/>}</button><span className="icon-btn" aria-label="Notifications"><Bell size={18}/></span><span className="profile-btn"><span>{initials}</span><b>{displayName}<small>{user.workspace_slug||user.role_code||"Admin"}</small></b></span><button className="icon-btn" onClick={logout} aria-label="Logout"><LogOut size={17}/></button></div>
    </header>
  );
}
