import { Activity, BarChart3, BookOpen, CreditCard, DatabaseZap, LayoutDashboard, Link2, ListTree, Megaphone, PhoneCall, PhoneForwarded, ScrollText, Settings, ShieldCheck, UserRoundCheck, Users } from "lucide-react";
import { NavLink } from "react-router-dom";

const groups = [
  ["VOICE OPERATIONS", [{to:"/overview",label:"Overview",icon:LayoutDashboard},{to:"/campaigns",label:"Campaigns",icon:Megaphone},{to:"/live-calls",label:"Live Calls",icon:Activity},{to:"/calls",label:"Call History",icon:PhoneCall},{to:"/callbacks",label:"Callback Inbox",icon:UserRoundCheck},{to:"/leads",label:"Lead Pipeline",icon:Users},{to:"/customers",label:"Customers",icon:Users},{to:"/knowledge-base",label:"Knowledge Base",icon:BookOpen},{to:"/analytics",label:"Analytics",icon:BarChart3}]],
  ["ADMINISTRATION", [{to:"/integrations",label:"Provider Credentials",icon:Link2},{to:"/integrations/crm",label:"CRM Integration",icon:DatabaseZap},{to:"/ivr",label:"IVR Menu",icon:ListTree},{to:"/transfers",label:"Human Transfer",icon:PhoneForwarded},{to:"/integrations/plivo-number",label:"Calling Number",icon:PhoneCall},{to:"/team",label:"Team & Roles",icon:Users},{to:"/billing",label:"Usage & Billing",icon:CreditCard},{to:"/security",label:"Security",icon:ShieldCheck},{to:"/audit-logs",label:"Audit Logs",icon:ScrollText},{to:"/settings",label:"Settings",icon:Settings}]],
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex h-full flex-col">
      <div className="mb-8 flex items-center gap-3 px-2">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 text-white">
          <PhoneCall size={22} />
        </div>
        <div>
          <p className="text-sm font-extrabold leading-tight text-slate-950">DigiDARA</p>
          <p className="text-xs font-semibold text-slate-500">AI Communications</p>
        </div>
      </div>
      <div className="nav-groups">
        {groups.map(([name,links]:any) => <section key={name}><small>{name}</small>{links.map((link:any) => (
          <NavLink
            key={link.to}
            to={link.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? "sidebar-link-active" : ""}`
            }
          >
            <link.icon size={18} />
            {link.label}
          </NavLink>
        ))}</section>)}
      </div>
      <div className="connection-card"><i/>Realtime connected<small>AI voice operations</small></div>
    </nav>
  );
}
