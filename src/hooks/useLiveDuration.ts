import { useEffect, useState } from "react";
import { liveDuration } from "../utils/formatDuration";

/**
 * Returns a live-updating elapsed-seconds count from a given ISO/MySQL timestamp.
 * Updates every second while the component is mounted.
 */
export function useLiveDuration(createdAt?: string | null): number {
  const [seconds, setSeconds] = useState(() => liveDuration(createdAt));

  useEffect(() => {
    if (!createdAt) return;
    const id = setInterval(() => {
      setSeconds(liveDuration(createdAt));
    }, 1000);
    return () => clearInterval(id);
  }, [createdAt]);

  return seconds;
}
