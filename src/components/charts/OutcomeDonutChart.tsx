import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

export interface OutcomePoint {
  name: string;
  value: number;
}

const colors = ["#4f46e5", "#10b981", "#f59e0b", "#ef4444", "#64748b"];

export function OutcomeDonutChart({ data }: { data: OutcomePoint[] }) {
  const safeData = data.length ? data : [{ name: "No calls", value: 1 }];
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie data={safeData} innerRadius={68} outerRadius={98} paddingAngle={4} dataKey="value">
          {safeData.map((entry, index) => (
            <Cell key={entry.name} fill={colors[index % colors.length]} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}
