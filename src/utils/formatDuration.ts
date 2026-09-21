export function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "--:--";
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.max(0, Math.floor(seconds % 60));
  return `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

export function liveDuration(createdAt?: string | null): number {
  if (!createdAt) return 0;
  const start = new Date(createdAt.replace(" ", "T")).getTime();
  if (Number.isNaN(start)) return 0;
  return Math.max(0, Math.floor((Date.now() - start) / 1000));
}
