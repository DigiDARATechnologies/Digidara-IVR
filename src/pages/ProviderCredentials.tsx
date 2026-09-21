import { KeyRound, Phone, Trash2 } from "lucide-react";
import { FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { useCredentialStatus, useRemoveCredential, useSaveCredential } from "../api/integrations";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import "./ProviderCredentials.css";

interface ProviderField {
  key: string;
  label: string;
  placeholder: string;
  secret?: boolean;
}

const PROVIDERS: {
  id: string;
  name: string;
  icon: typeof Phone;
  blurb: string;
  fields: ProviderField[];
}[] = [
  {
    id: "plivo",
    name: "Plivo",
    icon: Phone,
    blurb: "Your own Plivo account places outbound calls under your own number and billing, instead of the shared default.",
    fields: [
      { key: "auth_id", label: "Auth ID", placeholder: "MAxxxxxxxxxxxxxxxxxx" },
      { key: "auth_token", label: "Auth Token", placeholder: "••••••••••••••••", secret: true },
      { key: "from_number", label: "From Number", placeholder: "+15551234567" },
    ],
  },
  {
    id: "openai",
    name: "OpenAI",
    icon: KeyRound,
    blurb: "Your own OpenAI API key is used for the Realtime conversation engine on your calls, instead of the shared default.",
    fields: [
      { key: "api_key", label: "API Key", placeholder: "sk-••••••••••••••••", secret: true },
    ],
  },
];

export function ProviderCredentials() {
  const status = useCredentialStatus();
  const save = useSaveCredential();
  const remove = useRemoveCredential();
  const [forms, setForms] = useState<Record<string, Record<string, string>>>({});

  function fieldValue(providerId: string, key: string): string {
    return forms[providerId]?.[key] || "";
  }

  function setField(providerId: string, key: string, value: string) {
    setForms((current) => ({
      ...current,
      [providerId]: { ...current[providerId], [key]: value },
    }));
  }

  async function submit(providerId: string, event: FormEvent) {
    event.preventDefault();
    const fields = forms[providerId] || {};
    if (!Object.values(fields).some((value) => value.trim())) {
      toast.error("Enter at least one field before saving.");
      return;
    }
    try {
      await save.mutateAsync({ provider: providerId, fields });
      toast.success(`${providerId === "plivo" ? "Plivo" : "OpenAI"} credentials saved.`);
      setForms((current) => ({ ...current, [providerId]: {} }));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function clear(providerId: string) {
    try {
      await remove.mutateAsync(providerId);
      toast.success("Removed — calls will use the shared default credentials again.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  const statusByProvider = new Map((status.data || []).map((entry) => [entry.provider, entry]));

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Integrations</h1>
          <p className="text-sm text-slate-500">
            Connect your own provider accounts. Anything left unconfigured falls back to the shared workspace default.
          </p>
        </div>
      </div>
      <section className="credentials-grid">
        {PROVIDERS.map((provider) => {
          const entry = statusByProvider.get(provider.id);
          const Icon = provider.icon;
          return (
            <Card key={provider.id}>
              <div className="credentials-head">
                <div className="credentials-head-title">
                  <span className="credentials-icon"><Icon size={20} /></span>
                  <div>
                    <h2>{provider.name}</h2>
                    <p>{provider.blurb}</p>
                  </div>
                </div>
                {entry?.configured ? (
                  <Badge tone="green">Configured</Badge>
                ) : (
                  <Badge tone="gray">Using shared default</Badge>
                )}
              </div>
              {entry?.configured && (
                <p className="credentials-meta">
                  Ends in <strong>{entry.last_four || "····"}</strong>
                  {entry.rotated_at ? ` · updated ${entry.rotated_at}` : ""}
                </p>
              )}
              <form className="credentials-form" onSubmit={(event) => submit(provider.id, event)}>
                {provider.fields.map((field) => (
                  <label key={field.key}>
                    <span>{field.label}</span>
                    <input
                      type={field.secret ? "password" : "text"}
                      value={fieldValue(provider.id, field.key)}
                      onChange={(event) => setField(provider.id, field.key, event.target.value)}
                      placeholder={field.placeholder}
                      autoComplete="off"
                    />
                  </label>
                ))}
                <div className="credentials-actions">
                  <Button disabled={save.isPending}>
                    {save.isPending ? "Saving…" : entry?.configured ? "Update credentials" : "Save credentials"}
                  </Button>
                  {entry?.configured && (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => clear(provider.id)}
                      disabled={remove.isPending}
                    >
                      <Trash2 size={14} /> Remove
                    </Button>
                  )}
                </div>
              </form>
            </Card>
          );
        })}
      </section>
    </>
  );
}
