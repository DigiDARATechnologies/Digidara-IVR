import type { CallLog } from "../types";

type AnalysisShape = {
  summary?: unknown;
  quick_summary?: unknown;
  next_action?: unknown;
};

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function parsedAnalysis(raw?: string | null): AnalysisShape | null {
  if (!raw) return null;
  const cleaned = raw.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const parsed = JSON.parse(cleaned.slice(start, end + 1));
    return parsed && typeof parsed === "object" ? parsed as AnalysisShape : null;
  } catch {
    return null;
  }
}

function transcriptFallback(log: CallLog): string {
  const lines = (log.transcript || "").split("\n");
  const customerTurns = lines
    .map((line) => line.match(/^\s*(?:user|customer)\s*:\s*(.+)$/i)?.[1]?.trim() || "")
    .filter((turn) => turn.length > 8 && !/^(?:okay|ok|yes|no|thanks?|thank you|bye|goodbye)[.! ]*$/i.test(turn));
  const assistantTurns = lines
    .map((line) => line.match(/^\s*(?:assistant|ai assistant|ai)\s*:\s*(.+)$/i)?.[1]?.trim() || "")
    .filter((turn) => turn.length > 20 && !/^(?:welcome|hello|hi)\b/i.test(turn));
  if (!customerTurns.length) return "No meaningful customer response captured";
  const need = [...customerTurns].sort((a,b) => b.length-a.length)[0];
  const finalPosition = customerTurns[customerTurns.length-1];
  const discussion = [...assistantTurns].sort((a,b) => b.length-a.length)[0];
  const allCustomerText = customerTurns.join(" ").toLowerCase();
  const nextAction = allCustomerText.includes("visit")
    ? "Share the location and arrange course counselling when the customer visits."
    : allCustomerText.includes("contact") || allCustomerText.includes("team")
      ? "The counselling team should provide batch, fee, and enrolment details when contacted."
      : "No confirmed follow-up was captured; review the call before scheduling the next contact.";
  return [
    `Customer need: ${need}`,
    ...(discussion ? [`Discussion: ${discussion}`] : []),
    `Outcome: ${finalPosition === need ? "No separate final decision was captured." : finalPosition}`,
    `Next action: ${nextAction}`,
  ].slice(0,4).join("\n");
}

function isWeakLegacySummary(value?: string | null): boolean {
  const summary = (value || "").toLowerCase();
  return summary.startsWith("discussed: “")
    || summary.includes("no confirmed follow-up was captured");
}

export function callQuickSummary(log: CallLog): string {
  const quickParsed = parsedAnalysis(log.quick_summary);
  const summaryParsed = parsedAnalysis(log.summary);
  return text(quickParsed?.quick_summary)
    || (log.quick_summary && !quickParsed ? log.quick_summary.trim() : "")
    || text(summaryParsed?.quick_summary)
    || text(summaryParsed?.summary)
    || (log.summary && !summaryParsed && log.summary !== "Summary generation failed." ? log.summary.trim() : "")
    || transcriptFallback(log);
}

export function callFullSummary(log: CallLog): string {
  const parsed = parsedAnalysis(log.summary) || parsedAnalysis(log.quick_summary);
  const summary = text(parsed?.summary)
    || (log.summary && !parsedAnalysis(log.summary) && log.summary !== "Summary generation failed." && !isWeakLegacySummary(log.summary) ? log.summary.trim() : "")
    || transcriptFallback(log);
  const nextAction = text(parsed?.next_action);
  if (!nextAction || summary.toLowerCase().includes("next action")) return summary;
  return `${summary}\nNext action: ${nextAction}`;
}
