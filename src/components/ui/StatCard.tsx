import type { LucideIcon } from "lucide-react";
import { Card } from "./Card";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  hint: string;
  onClick?: () => void;
}

export function StatCard({ icon: Icon, label, value, hint, onClick }: StatCardProps) {
  return (
    <Card className={`transition hover:shadow-md ${onClick ? "cursor-pointer" : ""}`}>
      <div className="flex items-start justify-between" onClick={onClick} role={onClick ? "button" : undefined}>
        <div>
          <p className="text-sm font-semibold text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-extrabold text-slate-950">{value}</p>
          <p className="mt-1 text-sm text-slate-500">{hint}</p>
        </div>
        <div className="rounded-lg bg-indigo-50 p-3 text-indigo-600">
          <Icon size={22} />
        </div>
      </div>
    </Card>
  );
}
