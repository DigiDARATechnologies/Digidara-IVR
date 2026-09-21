import { Gauge } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { useLeadScore } from "../api/leadScore";
import { getErrorMessage } from "../api/client";
import { ScoreGauge } from "../components/charts/ScoreGauge";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Toggle } from "../components/ui/Toggle";
import type { LeadScoreRequest } from "../types";
import "./LeadScoring.css";

const initial: LeadScoreRequest = {
  interested: false,
  budget: false,
  decision_maker: false,
  callback_requested: false
};

export function LeadScoring() {
  const [values, setValues] = useState<LeadScoreRequest>(initial);
  const score = useLeadScore();

  async function calculate() {
    try {
      await score.mutateAsync(values);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  const result = score.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Lead Scoring</h1>
          <p className="text-sm text-slate-500">Preview a rule-based score. Production lead scores come from post-call conversation analysis.</p>
        </div>
      </div>
      <section className="lead-grid">
        <Card>
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-3 text-indigo-600">
              <Gauge size={20} />
            </div>
            <h2 className="text-lg font-bold">Signals</h2>
          </div>
          <div className="space-y-3">
            {(Object.keys(values) as Array<keyof LeadScoreRequest>).map((key) => (
              <Toggle
                key={key}
                label={key.replace(/_/g, " ")}
                checked={values[key]}
                onChange={(checked) => setValues({ ...values, [key]: checked })}
              />
            ))}
          </div>
          <Button className="mt-4 w-full" onClick={calculate} disabled={score.isPending}>Calculate</Button>
        </Card>
        <Card className="flex flex-col items-center justify-center">
          <ScoreGauge score={result?.lead_score || 0} />
          <div className="mt-6">
            <Badge tone={result?.status === "HOT_LEAD" ? "green" : result?.status === "WARM_LEAD" ? "amber" : "gray"}>
              {result?.status || "Not scored"}
            </Badge>
          </div>
          {result && <p className="mt-3 text-center text-xs text-slate-500">Preview only · not saved to the customer or call</p>}
        </Card>
      </section>
    </>
  );
}
