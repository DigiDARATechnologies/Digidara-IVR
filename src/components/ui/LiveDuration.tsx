import { useLiveDuration } from "../../hooks/useLiveDuration";
import { formatDuration } from "../../utils/formatDuration";

interface LiveDurationProps {
  createdAt?: string | null;
}

/**
 * Renders a ticking mm:ss duration for a live/in-progress call.
 * Automatically updates every second via setInterval.
 */
export function LiveDuration({ createdAt }: LiveDurationProps) {
  const seconds = useLiveDuration(createdAt);
  return <>{formatDuration(seconds)}</>;
}
