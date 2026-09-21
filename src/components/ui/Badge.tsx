import { statusTone } from "../../utils/statusBadge";

interface BadgeProps {
  children: string;
  tone?: "green" | "amber" | "red" | "blue" | "gray";
}

export function Badge({ children, tone }: BadgeProps) {
  const resolved = tone || statusTone(children);
  return <span className={`badge-${resolved}`}>{children.replace(/_/g, " ")}</span>;
}
