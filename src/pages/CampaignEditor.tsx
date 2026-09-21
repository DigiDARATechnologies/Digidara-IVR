import { FormEvent } from "react";
import { Button } from "../components/ui/Button";
import type { CampaignPayload } from "../types";

const placeholders = ["{customer_name}", "{name}", "{customer_language}", "{language}"];

const EXAMPLE_PROMPT = `You are a friendly admissions advisor calling on behalf of DigiDara Technologies.

Your goal:
1. Greet {customer_name} warmly, introduce yourself as calling from DigiDara Technologies.
2. Mention you are following up on their enquiry about our AI/ML training programs.
3. Ask if they are still interested and when they are planning to join.
4. Answer any questions they have about courses, fees, or internships honestly.
5. If they confirm a joining date, note it and ask if they would like a reminder call one day before.
6. If they want to delay, ask for a callback date and time.

Keep responses warm, natural, and brief — 2-3 sentences at most.`;

interface CampaignEditorProps {
  value: CampaignPayload;
  onChange: (value: CampaignPayload) => void;
  onSubmit: () => void;
  saving: boolean;
}

export function CampaignEditor({ value, onChange, onSubmit, saving }: CampaignEditorProps) {
  const tamilCharacters = (value.ai_prompt.match(/[\u0B80-\u0BFF]/g) || []).length;
  const estimatedTokens = Math.ceil(
    tamilCharacters / 1.8 + (value.ai_prompt.length - tamilCharacters) / 4,
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  function insertPlaceholder(token: string) {
    onChange({ ...value, ai_prompt: `${value.ai_prompt} ${token}`.trim() });
  }

  function loadExample() {
    onChange({ ...value, ai_prompt: EXAMPLE_PROMPT });
  }

  return (
    <form className="campaign-editor" onSubmit={submit}>
      <label>
        <span className="label">Campaign Name</span>
        <input
          className="field"
          placeholder="e.g. AI Course Follow-up — English"
          value={value.campaign_name}
          onChange={(e) => onChange({ ...value, campaign_name: e.target.value })}
        />
      </label>

      <label>
        <span className="label">Objective <span className="text-slate-400 font-normal">(internal note)</span></span>
        <textarea
          className="field min-h-16"
          placeholder="e.g. Follow up with students who enquired about AI courses and confirm joining date"
          value={value.objective}
          onChange={(e) => onChange({ ...value, objective: e.target.value })}
        />
      </label>

      {/* Tips box */}
      <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-900 space-y-1.5">
        <p className="font-bold text-indigo-800">💡 How the AI Prompt works</p>
        <p>The prompt controls the conversation <strong>after one system-managed greeting</strong>. The assistant will:</p>
        <ol className="list-decimal list-inside space-y-1 text-indigo-800">
          <li>Deliver one consistent welcome, then follow your campaign objective without repeating the introduction</li>
          <li>Answer customer questions using the DigiDara knowledge base (courses, services, internships)</li>
          <li>Follow the flow you define in the prompt</li>
        </ol>
        <p className="text-indigo-700 text-xs">Use the placeholders below to personalize. A normal campaign is usually 150–450 estimated tokens.</p>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="label">Prompt placeholders</span>
          <button
            type="button"
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            onClick={loadExample}
          >
            Load example prompt ↗
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {placeholders.map((token) => (
            <button
              key={token}
              type="button"
              className="prompt-chip"
              onClick={() => insertPlaceholder(token)}
            >
              {token}
            </button>
          ))}
        </div>
      </div>

      <label>
        <span className="label">AI Prompt</span>
        <textarea
          className="field min-h-56 font-mono text-sm"
          placeholder="Write your campaign prompt here… or click 'Load example prompt' above."
          value={value.ai_prompt}
          onChange={(e) => onChange({ ...value, ai_prompt: e.target.value })}
        />
        <span className="text-xs text-slate-400">
          {value.ai_prompt.length} characters · about {estimatedTokens} estimated tokens
        </span>
      </label>

      <p className="text-xs text-emerald-700">
        For Tamil calls, enter the objective, approved facts, required questions,
        prohibited claims, and closing action. The agent converts this into natural
        spoken Tamil. Do not write a word-for-word speech script.
      </p>

      {estimatedTokens > 450 && (
        <p className="text-sm font-semibold text-amber-600">
          This campaign is above the usual range. It will be compacted safely, but
          removing repeated lines can reduce latency and cost.
        </p>
      )}

      <Button disabled={saving} className="w-full">
        {saving ? "Saving…" : "Save campaign"}
      </Button>
    </form>
  );
}
