import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Building2, ShieldCheck } from "lucide-react";
import { createWorkspace, googleLogin } from "../api/auth";
import { getErrorMessage } from "../api/client";
import { Button } from "../components/ui/Button";
import { GoogleSignInButton } from "../components/GoogleSignInButton";
import "./Login.css";

export function AdminOnboarding() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    organization_name: "",
    workspace_slug: "",
    full_name: "",
    email: "",
    password: "",
    confirm: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [slugEdited, setSlugEdited] = useState(false);

  if (localStorage.getItem("digidara-token")) {
    return <Navigate to="/" replace />;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (form.password !== form.confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const response = await createWorkspace({
        organization_name: form.organization_name,
        workspace_slug: form.workspace_slug,
        full_name: form.full_name,
        email: form.email,
        password: form.password,
      });
      localStorage.setItem("digidara-token", response.token);
      localStorage.setItem("digidara-user", JSON.stringify(response.user));
      localStorage.setItem("digidara-user-email", response.user.email);
      localStorage.setItem("digidara-workspace-slug", response.user.workspace_slug);
      navigate("/");
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleGoogleCredential(credential: string) {
    setError("");
    setBusy(true);
    try {
      const response = await googleLogin(credential);
      localStorage.setItem("digidara-token", response.token);
      localStorage.setItem("digidara-user", JSON.stringify(response.user));
      localStorage.setItem("digidara-user-email", response.user.email);
      localStorage.setItem("digidara-workspace-slug", response.user.workspace_slug);
      navigate("/");
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function setWorkspaceName(value: string) {
    const generatedSlug = value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 100);
    setForm((current) => ({
      ...current,
      organization_name: value,
      workspace_slug: slugEdited ? current.workspace_slug : generatedSlug,
    }));
  }

  return (
    <main className="login-page">
      <section className="login-panel onboarding-panel">
        <aside className="login-hero">
          <div className="login-brand"><span><Building2 /></span><div><b>DigiDara AI</b><small>Secure workspace setup</small></div></div>
          <div className="login-message">
            <span className="login-kicker">WORKSPACE REGISTRATION</span>
            <h1>Create an isolated organization workspace.</h1>
            <p>Create your organization and administrator account together, then sign in to your private workspace.</p>
          </div>
        </aside>
        <form className="login-form" onSubmit={submit}>
          <div className="login-form-head"><h2>New workspace</h2><p>Choose the organization name and workspace ID used during sign-in.</p></div>
          <div className="login-fields">
            <GoogleSignInButton onCredential={handleGoogleCredential} text="signup_with" />
            <div className="login-divider"><span>or set up manually</span></div>
            <label><span>Organization name</span><input type="text" value={form.organization_name} onChange={(event) => setWorkspaceName(event.target.value)} required minLength={2} maxLength={180} /></label>
            <label><span>Workspace ID</span><input type="text" value={form.workspace_slug} onChange={(event) => { setSlugEdited(true); setForm({ ...form, workspace_slug: event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") }); }} placeholder="company-name" required minLength={3} maxLength={100} /></label>
            <label><span>Administrator name</span><input type="text" value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required minLength={2} maxLength={150} /></label>
            <label><span>Work email</span><input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label>
            <label><span>Password (10+ characters)</span><input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required minLength={10} maxLength={128} /></label>
            <label><span>Confirm password</span><input type="password" value={form.confirm} onChange={(event) => setForm({ ...form, confirm: event.target.value })} required /></label>
            {error && <p className="login-error" role="alert">{error}</p>}
            <Button disabled={busy}>{busy ? "Creating…" : "Create workspace"}</Button>
            <button className="onboarding-link" type="button" onClick={() => navigate("/login")}><ShieldCheck /> Return to sign in</button>
          </div>
        </form>
      </section>
    </main>
  );
}
