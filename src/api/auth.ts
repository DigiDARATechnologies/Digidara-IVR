import axios from "axios";
import { api } from "./client";
export interface AdminPayload { full_name:string; email:string; password:string; bootstrap_key?:string }
export interface WorkspacePayload { organization_name:string; workspace_slug:string; full_name:string; email:string; password:string }
export interface LoginFailure {
  code?: string;
  message: string;
  attempts_remaining?: number;
  retry_after_seconds?: number;
}
export async function login(email:string,password:string,workspace_slug:string){return (await api.post("/auth/login",{email,password,workspace_slug})).data}
export async function googleLogin(credential:string){return (await api.post("/auth/google",{credential})).data}
export function getLoginFailure(error:unknown):LoginFailure {
  if (axios.isAxiosError(error)) {
    const detail=error.response?.data?.detail;
    if (detail && typeof detail === "object") {
      return {
        code:typeof detail.code === "string"?detail.code:undefined,
        message:typeof detail.message === "string"?detail.message:"Sign-in failed",
        attempts_remaining:typeof detail.attempts_remaining === "number"?detail.attempts_remaining:undefined,
        retry_after_seconds:typeof detail.retry_after_seconds === "number"?detail.retry_after_seconds:undefined,
      };
    }
    if (typeof detail === "string") return {message:detail};
    return {message:error.message};
  }
  return {message:error instanceof Error?error.message:"Sign-in failed"};
}
export async function authStatus(){return (await api.get("/auth/status")).data as {needs_admin_onboarding:boolean}}
export async function bootstrapAdmin(payload:AdminPayload){return (await api.post("/auth/bootstrap-admin",payload)).data}
export async function createWorkspace(payload:WorkspacePayload){return (await api.post("/auth/workspaces",payload)).data}
export async function createAdmin(payload:AdminPayload){return (await api.post("/admin/users",payload)).data}
export async function updateOrganizationName(name:string){return (await api.patch("/organizations/me",{name})).data as {organization_name:string}}
