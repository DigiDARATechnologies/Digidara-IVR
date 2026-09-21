export type BadgeTone = "green" | "amber" | "red" | "blue" | "gray";

export function normalizedStatus(status?: string | null, callStatus?: string | null): string {
  return (callStatus || status || "idle").trim().toLowerCase();
}

export function statusTone(status?: string | null, callStatus?: string | null): BadgeTone {
  const value = normalizedStatus(status, callStatus);
  if (["completed", "interested", "hot_lead", "hot lead"].includes(value)) return "green";
  if (["in-progress", "ongoing", "ringing", "initiated"].includes(value)) return "amber";
  if (["failed", "no-answer", "no answer", "busy", "canceled", "cancelled"].includes(value)) return "red";
  if (["queued", "queue", "pending"].includes(value)) return "blue";
  return "gray";
}

export function isLiveStatus(status?: string | null, callStatus?: string | null, createdAt?: string | null): boolean {
  if (createdAt) {
    const created = new Date(createdAt.replace(" ", "T")).getTime();
    if (Number.isFinite(created) && Date.now() - created > 2 * 60 * 60 * 1000) return false;
  }
  return ["ringing", "in-progress", "ongoing", "queued", "queue", "initiated"].includes(
    normalizedStatus(status, callStatus)
  );
}
