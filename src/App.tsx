import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { ProtectedRoute } from "./components/layout/ProtectedRoute";
import { Calls } from "./pages/Calls";
import { Campaigns } from "./pages/Campaigns";
import { Login } from "./pages/Login";
import { AdminOnboarding } from "./pages/AdminOnboarding";
import { PlivoProvisioning } from "./pages/PlivoProvisioning";
import { FacilityConsole } from "./pages/FacilityConsole";
import { CallbackInbox } from "./pages/CallbackInbox";
import { Customers } from "./pages/Customers";
import { CrmIntegration } from "./pages/CrmIntegration";
import { OrganizationKnowledgeBase } from "./pages/OrganizationKnowledgeBase";
import { ProviderCredentials } from "./pages/ProviderCredentials";
import { TransferSettings } from "./pages/TransferSettings";
import { IvrSettings } from "./pages/IvrSettings";
import { AdminPage, Analytics, CallDetail, CampaignBuilder, Customer360, LeadsPipeline, LiveOperations, OverviewPage, SettingsCenter } from "./pages/ProductPages";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<AdminOnboarding />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<OverviewPage />} />
            <Route path="/facility-console" element={<FacilityConsole />} />
            <Route path="/live-calls" element={<LiveOperations />} />
            <Route path="/calls" element={<Calls />} />
            <Route path="/calls/:id" element={<CallDetail />} />
            <Route path="/campaigns" element={<Campaigns />} />
            <Route path="/campaigns/new" element={<CampaignBuilder />} />
            <Route path="/campaigns/:id/edit" element={<CampaignBuilder />} />
            <Route path="/callbacks" element={<CallbackInbox />} />
            <Route path="/leads" element={<LeadsPipeline />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/customers/:id" element={<Customer360 />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/integrations" element={<ProviderCredentials />} />
            <Route path="/integrations/crm" element={<CrmIntegration />} />
            <Route path="/knowledge-base" element={<OrganizationKnowledgeBase />} />
            <Route path="/transfers" element={<TransferSettings />} />
            <Route path="/ivr" element={<IvrSettings />} />
            <Route path="/integrations/plivo-number" element={<PlivoProvisioning />} />
            <Route path="/team" element={<AdminPage type="team" />} />
            <Route path="/billing" element={<AdminPage type="billing" />} />
            <Route path="/audit-logs" element={<AdminPage type="audit" />} />
            <Route path="/security" element={<AdminPage type="security" />} />
            <Route path="/settings" element={<SettingsCenter />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
