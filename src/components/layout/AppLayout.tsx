import { ArrowLeft, ChevronRight, Home, X } from "lucide-react";
import { useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const parts = location.pathname.split("/").filter(Boolean);
  const labels: Record<string,string> = {overview:"Overview","facility-console":"Facility Voice Console","live-calls":"Live Voice Operations",calls:"Call History",campaigns:"Campaigns",new:"New Campaign",edit:"Edit",callbacks:"Callback Inbox",leads:"Lead Pipeline",customers:"Customers","knowledge-base":"Knowledge Base",analytics:"Analytics",integrations:"Integrations",crm:"CRM Integration",ivr:"IVR Menu",transfers:"Human Transfer","plivo-number":"Calling Number",team:"Team & Roles",billing:"Usage & Billing",security:"Security","audit-logs":"Audit Logs",settings:"Settings"};
  const breadcrumbLabels = parts.map(x=>labels[x] || (/^\d+$/.test(x)?"Details":x));
  const currentLabel = breadcrumbLabels[breadcrumbLabels.length - 1];
  function goBack() {
    if (location.pathname.startsWith("/calls/")) return navigate("/calls");
    navigate("/overview");
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Sidebar />
      </aside>
      <Topbar onMenu={() => setMobileOpen(true)} />
      {mobileOpen && (
        <>
          <div className="drawer-backdrop" onClick={() => setMobileOpen(false)} />
          <aside className="mobile-drawer">
            <button className="mobile-drawer-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={18}/></button>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </>
      )}
      <main className="page-wrap">
        {parts.length > 0 && (
          <nav className="page-navigation" aria-label="Page navigation">
            <button type="button" className="back-btn" onClick={goBack}>
              <ArrowLeft size={16}/> Back
            </button>
            <div className="breadcrumbs">
              <Link to="/" aria-label="Overview"><Home size={14}/></Link>
              <ChevronRight size={13}/>
              <span>{currentLabel}</span>
            </div>
          </nav>
        )}
        <Outlet />
      </main>
    </div>
  );
}
