import { FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { updateOrganizationName } from "../api/auth";
import { getErrorMessage } from "../api/client";
import { Button } from "./ui/Button";

function currentOrganizationName(): string {
  try {
    const user = JSON.parse(localStorage.getItem("digidara-user") || "{}") as { organization_name?: string };
    return user.organization_name || "";
  } catch {
    return "";
  }
}

export function OrganizationNameForm() {
  const [name, setName] = useState(currentOrganizationName());
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 2) {
      toast.error("Enter a name with at least 2 characters.");
      return;
    }
    setSaving(true);
    try {
      const result = await updateOrganizationName(trimmed);
      const user = JSON.parse(localStorage.getItem("digidara-user") || "{}");
      localStorage.setItem(
        "digidara-user",
        JSON.stringify({ ...user, organization_name: result.organization_name }),
      );
      toast.success("Organization name updated — your AI will use it on the next call.");
      window.location.reload();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="space-y-3" onSubmit={handleSubmit}>
      <p className="text-sm text-slate-500">
        This is your business name as customers hear it — your AI agent introduces itself with this name at
        the start of every call.
      </p>
      <label>
        <span className="label">Organization name</span>
        <input className="field" value={name} onChange={(event) => setName(event.target.value)} maxLength={180} />
      </label>
      <Button disabled={saving}>{saving ? "Saving…" : "Save name"}</Button>
    </form>
  );
}
