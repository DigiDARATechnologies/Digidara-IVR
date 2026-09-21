import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import {
  DaySchedule,
  useBusinessHours,
  useBusinessHoursStatus,
  useSaveBusinessHours,
} from "../api/businessHours";
import { getErrorMessage } from "../api/client";
import { Button } from "./ui/Button";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const COMMON_TIMEZONES = [
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Europe/London",
  "America/New_York",
  "America/Los_Angeles",
  "UTC",
];

function defaultWeek(): DaySchedule[] {
  return DAY_LABELS.map((_, day_of_week) => ({
    day_of_week,
    is_closed: day_of_week >= 5, // Saturday/Sunday closed by default
    open_time: day_of_week >= 5 ? null : "09:00",
    close_time: day_of_week >= 5 ? null : "18:00",
  }));
}

export function BusinessHoursForm() {
  const businessHours = useBusinessHours();
  const status = useBusinessHoursStatus();
  const save = useSaveBusinessHours();

  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [days, setDays] = useState<DaySchedule[]>(defaultWeek());

  useEffect(() => {
    if (!businessHours.data) return;
    setTimezone(businessHours.data.timezone || "Asia/Kolkata");
    if (businessHours.data.configured && businessHours.data.days.length === 7) {
      setDays([...businessHours.data.days].sort((a, b) => a.day_of_week - b.day_of_week));
    }
  }, [businessHours.data]);

  function updateDay(day_of_week: number, patch: Partial<DaySchedule>) {
    setDays((current) =>
      current.map((day) => (day.day_of_week === day_of_week ? { ...day, ...patch } : day)),
    );
  }

  async function handleSave() {
    for (const day of days) {
      if (!day.is_closed && (!day.open_time || !day.close_time)) {
        toast.error(`Set both an open and close time for ${DAY_LABELS[day.day_of_week]}, or mark it closed.`);
        return;
      }
      if (!day.is_closed && day.open_time! >= day.close_time!) {
        toast.error(`${DAY_LABELS[day.day_of_week]}'s open time must be before its close time.`);
        return;
      }
    }
    try {
      await save.mutateAsync({ timezone, days });
      toast.success("Business hours saved.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  if (businessHours.isLoading) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        Calls to your number outside these hours get a "we're currently closed" message instead of
        reaching the AI receptionist.
        {businessHours.data && !businessHours.data.configured && (
          <> No schedule is set yet, so calls are answered around the clock.</>
        )}
      </p>

      {status.data && (
        <p className="text-sm font-medium">
          Right now:{" "}
          <span className={status.data.is_open ? "text-emerald-600" : "text-rose-600"}>
            {status.data.is_open ? "Open" : "Closed"}
          </span>
          {status.data.configured && (
            <span className="text-slate-400"> ({status.data.local_time.slice(0, 16).replace("T", " ")})</span>
          )}
        </p>
      )}

      <label className="block">
        <span className="label">Timezone</span>
        <select className="field" value={timezone} onChange={(event) => setTimezone(event.target.value)}>
          {[timezone, ...COMMON_TIMEZONES.filter((tz) => tz !== timezone)].map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </label>

      <div className="space-y-2">
        {days.map((day) => (
          <div key={day.day_of_week} className="flex flex-wrap items-center gap-3">
            <span className="w-24 text-sm font-medium">{DAY_LABELS[day.day_of_week]}</span>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={day.is_closed}
                onChange={(event) =>
                  updateDay(day.day_of_week, {
                    is_closed: event.target.checked,
                    open_time: event.target.checked ? null : day.open_time || "09:00",
                    close_time: event.target.checked ? null : day.close_time || "18:00",
                  })
                }
              />
              Closed
            </label>
            {!day.is_closed && (
              <>
                <input
                  type="time"
                  className="field"
                  value={day.open_time || ""}
                  onChange={(event) => updateDay(day.day_of_week, { open_time: event.target.value })}
                />
                <span className="text-sm text-slate-400">to</span>
                <input
                  type="time"
                  className="field"
                  value={day.close_time || ""}
                  onChange={(event) => updateDay(day.day_of_week, { close_time: event.target.value })}
                />
              </>
            )}
          </div>
        ))}
      </div>

      <Button disabled={save.isPending} onClick={handleSave}>
        {save.isPending ? "Saving…" : "Save business hours"}
      </Button>
    </div>
  );
}
