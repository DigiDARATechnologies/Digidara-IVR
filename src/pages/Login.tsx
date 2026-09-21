import { Eye, EyeOff, Mic2, Moon, ShieldCheck, Sun } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getLoginFailure, googleLogin, login } from "../api/auth";
import { getErrorMessage } from "../api/client";
import { Button } from "../components/ui/Button";
import { GoogleSignInButton } from "../components/GoogleSignInButton";
import "./Login.css";

const LOGIN_LOCK_STORAGE_KEY = "digidara-login-lock";

function readStoredLock(email: string, workspaceSlug: string): number {
  const stored = localStorage.getItem(LOGIN_LOCK_STORAGE_KEY);
  if (!stored) return 0;
  try {
    const lock = JSON.parse(stored) as { email?: string; workspace_slug?: string; until?: number };
    if (lock.email !== email.trim().toLowerCase() || lock.workspace_slug !== workspaceSlug.trim().toLowerCase()) return 0;
    return Math.max(0, Math.ceil((Number(lock.until) - Date.now()) / 1000));
  } catch {
    localStorage.removeItem(LOGIN_LOCK_STORAGE_KEY);
    return 0;
  }
}

function formatCountdown(seconds: number): string {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [workspaceSlug, setWorkspaceSlug] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [lockSeconds, setLockSeconds] = useState(0);
  const [dark, setDark] = useState(() => localStorage.getItem("digidara-theme") === "dark");

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("digidara-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    const rememberedEmail = localStorage.getItem("digidara-user-email") || "";
    const rememberedWorkspace = localStorage.getItem("digidara-workspace-slug") || "";
    setEmail(rememberedEmail);
    setWorkspaceSlug(rememberedWorkspace);
    setLockSeconds(readStoredLock(rememberedEmail, rememberedWorkspace));
  }, []);

  useEffect(() => {
    if (lockSeconds <= 0) return;
    const timer = window.setInterval(() => {
      setLockSeconds((value) => {
        const next = Math.max(0, value - 1);
        if (next === 0) localStorage.removeItem(LOGIN_LOCK_STORAGE_KEY);
        return next;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [lockSeconds > 0]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (lockSeconds > 0) return;
    setError("");
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setError("Enter a valid work email address.");
      return;
    }
    if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(workspaceSlug) || workspaceSlug.length < 3) {
      setError("Enter your workspace ID, for example company-name.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await login(email, password, workspaceSlug.trim().toLowerCase());
      localStorage.removeItem(LOGIN_LOCK_STORAGE_KEY);
      localStorage.setItem("digidara-token", response.token);
      localStorage.setItem("digidara-user", JSON.stringify(response.user));
      if (remember) {
        localStorage.setItem("digidara-user-email", email);
        localStorage.setItem("digidara-workspace-slug", response.user.workspace_slug);
      } else {
        localStorage.removeItem("digidara-user-email");
        localStorage.removeItem("digidara-workspace-slug");
      }
      navigate("/");
    } catch (caught) {
      const failure = getLoginFailure(caught);
      if (failure.retry_after_seconds) {
        const seconds = Math.max(1, Math.ceil(failure.retry_after_seconds));
        setLockSeconds(seconds);
        localStorage.setItem(LOGIN_LOCK_STORAGE_KEY, JSON.stringify({
          email: email.trim().toLowerCase(),
          workspace_slug: workspaceSlug.trim().toLowerCase(),
          until: Date.now() + seconds * 1000,
        }));
      } else if (failure.attempts_remaining != null) {
        const label = failure.attempts_remaining === 1 ? "attempt" : "attempts";
        setError(`${failure.message}. ${failure.attempts_remaining} ${label} remaining.`);
      } else {
        setError(failure.message || getErrorMessage(caught));
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGoogleCredential(credential: string) {
    setError("");
    setSubmitting(true);
    try {
      const response = await googleLogin(credential);
      localStorage.removeItem(LOGIN_LOCK_STORAGE_KEY);
      localStorage.setItem("digidara-token", response.token);
      localStorage.setItem("digidara-user", JSON.stringify(response.user));
      if (remember) {
        localStorage.setItem("digidara-user-email", response.user.email);
        localStorage.setItem("digidara-workspace-slug", response.user.workspace_slug);
      }
      navigate("/");
    } catch (caught) {
      const failure = getLoginFailure(caught);
      setError(failure.message || getErrorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  const lockTime = formatCountdown(lockSeconds);

  return (
    <main className="login-page">
      <button className="login-theme" onClick={() => setDark((value) => !value)} aria-label="Change theme">
        {dark ? <Sun /> : <Moon />}
      </button>
      <section className="login-panel">
        <aside className="login-hero">
          <div className="login-brand"><span><Mic2 /></span><div><b>DigiDara AI</b><small>Voice Assistant</small></div></div>
          <div className="login-message">
            <span className="login-kicker">ENGLISH + TAMIL REALTIME AI</span>
            <h1>Human conversations.<br />AI-powered scale.</h1>
            <p>Manage customers, campaigns, live calls and qualified leads from one secure workspace.</p>
            <div className="login-points"><span><ShieldCheck />Tenant-ready data controls</span><span><Mic2 />Bilingual realtime calling</span></div>
          </div>
        </aside>
        <form className="login-form" onSubmit={submit}>
          <div className="login-form-head"><span className="login-mobile-logo"><Mic2 /></span><h2>Welcome back</h2><p>Sign in to continue to your voice operations workspace.</p></div>
          <div className="login-fields">
            <GoogleSignInButton onCredential={handleGoogleCredential} text="signin_with" dark={dark} />
            <div className="login-divider"><span>or sign in with workspace ID</span></div>
            <label><span>Workspace ID</span><input type="text" autoComplete="organization" value={workspaceSlug} onChange={(event) => setWorkspaceSlug(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} placeholder="company-name" disabled={lockSeconds > 0} required /></label>
            <label><span>Work email</span><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" disabled={lockSeconds > 0} /></label>
            <label><span>Password</span><div className="password-field"><input type={show ? "text" : "password"} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" disabled={lockSeconds > 0} /><button type="button" onClick={() => setShow((value) => !value)} aria-label={show ? "Hide password" : "Show password"} disabled={lockSeconds > 0}>{show ? <EyeOff /> : <Eye />}</button></div></label>
            <div className="login-options"><label><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />Remember me</label><span>Secure admin access</span></div>
            {error && <p className="login-error" role="alert">{error}</p>}
            {lockSeconds > 0 && <p className="login-lockout" role="alert">Account temporarily locked. Try again in <strong>{lockTime}</strong>.</p>}
            <Button className="login-submit" disabled={submitting || lockSeconds > 0}>{submitting ? "Signing in…" : lockSeconds > 0 ? `Try again in ${lockTime}` : "Sign in"}</Button>
            <button className="onboarding-link" type="button" onClick={() => navigate("/onboarding")}>Create a workspace</button>
          </div>
        </form>
      </section>
    </main>
  );
}
