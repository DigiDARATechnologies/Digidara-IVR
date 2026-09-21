import { FileSpreadsheet, RefreshCw, Sheet, UploadCloud } from "lucide-react";
import { ChangeEvent, FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { useCampaigns } from "../api/campaigns";
import { useRunSheet, useRunUpload, useSheetStatus } from "../api/calls";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import "./BulkCalling.css";

const columns = ["Name", "Phone", "Language", "Status", "Investigated Course", "Internship or Course", "Course Duration"];

type Source = "sheet" | "upload";

export function BulkCalling() {
  const campaigns = useCampaigns();
  const runSheet = useRunSheet();
  const runUpload = useRunUpload();
  const [source, setSource] = useState<Source>("sheet");
  const [sheetUrl, setSheetUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [campaignId, setCampaignId] = useState("");
  const [triggeredUrl, setTriggeredUrl] = useState("");
  const [lastResult, setLastResult] = useState<{ message: string; count: number } | null>(null);

  const sheetStatus = useSheetStatus(triggeredUrl, Boolean(triggeredUrl));
  const statusRows = sheetStatus.data?.rows || [];
  const busy = runSheet.isPending || runUpload.isPending;

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] || null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaignId) {
      toast.error("Select a campaign.");
      return;
    }
    try {
      if (source === "sheet") {
        if (!sheetUrl.startsWith("http")) {
          toast.error("Enter a Google Sheet URL.");
          return;
        }
        const result = await runSheet.mutateAsync({ sheet_url: sheetUrl, campaign_id: Number(campaignId) });
        toast.success(result.message);
        setLastResult({ message: result.message, count: result.calls_triggered?.length || 0 });
        setTriggeredUrl(result.sheet_url || sheetUrl);
      } else {
        if (!file) {
          toast.error("Choose a .csv or .xlsx file.");
          return;
        }
        const result = await runUpload.mutateAsync({ file, campaignId: Number(campaignId) });
        toast.success(result.message);
        setLastResult({ message: result.message, count: result.calls_triggered?.length || 0 });
        if (result.sheet_url) setTriggeredUrl(result.sheet_url);
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Bulk Calling</h1>
          <p className="text-sm text-slate-500">Launch queued calls from a Google Sheet or an uploaded file.</p>
        </div>
      </div>
      <section className="bulk-grid">
        <Card>
          <div className="source-toggle" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={source === "sheet"}
              className={source === "sheet" ? "active" : ""}
              onClick={() => setSource("sheet")}
            >
              <Sheet size={15} /> Google Sheet URL
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={source === "upload"}
              className={source === "upload" ? "active" : ""}
              onClick={() => setSource("upload")}
            >
              <FileSpreadsheet size={15} /> Upload file
            </button>
          </div>
          <form className="space-y-4" onSubmit={submit}>
            {source === "sheet" ? (
              <label>
                <span className="label">Google Sheet URL</span>
                <input className="field" value={sheetUrl} onChange={(event) => setSheetUrl(event.target.value)} placeholder="https://docs.google.com/spreadsheets/d/..." />
              </label>
            ) : (
              <label>
                <span className="label">Lead list (.csv or .xlsx)</span>
                <input className="field" type="file" accept=".csv,.xlsx,.xlsm" onChange={handleFileChange} />
                {file && <span className="upload-filename">{file.name}</span>}
              </label>
            )}
            <label>
              <span className="label">Campaign</span>
              <select className="field" value={campaignId} onChange={(event) => setCampaignId(event.target.value)}>
                <option value="">Select campaign</option>
                {(campaigns.data || []).map((campaign) => (
                  <option key={campaign.id} value={campaign.id}>{campaign.campaign_name}</option>
                ))}
              </select>
            </label>
            <Button disabled={busy}>
              <UploadCloud size={16} />
              {busy ? "Starting…" : source === "sheet" ? "Run sheet" : "Run upload"}
            </Button>
          </form>
          {lastResult && (
            <div className="mt-6 table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Result</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Message</td>
                    <td>{lastResult.message}</td>
                  </tr>
                  <tr>
                    <td>Calls triggered</td>
                    <td>{lastResult.count}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card>
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-3 text-indigo-600">
              <Sheet size={20} />
            </div>
            <h2 className="text-lg font-bold">Expected columns</h2>
          </div>
          <div className="sheet-columns">
            {columns.map((column) => (
              <span key={column} className="rounded-lg bg-slate-50 px-3 py-2 font-semibold">{column}</span>
            ))}
          </div>
          <p className="upload-hint">Same column recognition applies to uploaded files as to Google Sheets — header names like "Phone No" or "Ph No" are matched automatically either way.</p>
        </Card>
      </section>
      {triggeredUrl && (
        <section className="mt-6">
          <Card>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold">Campaign progress</h2>
              <Button
                type="button"
                variant="ghost"
                onClick={() => sheetStatus.refetch()}
                disabled={sheetStatus.isFetching}
              >
                <RefreshCw size={14} className={sheetStatus.isFetching ? "animate-spin" : ""} />
                Refresh now
              </Button>
            </div>
            {sheetStatus.isLoading ? (
              <p className="text-sm text-slate-500">Loading status…</p>
            ) : statusRows.length === 0 ? (
              <p className="text-sm text-slate-500">No rows found yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Name</th>
                      <th>Phone</th>
                      <th>Language</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statusRows.map((row) => (
                      <tr
                        key={row.row_number}
                        className={row.status.trim().toLowerCase() === "ongoing" ? "row-active" : ""}
                      >
                        <td>{row.row_number}</td>
                        <td>{row.name || "—"}</td>
                        <td>{row.phone || "—"}</td>
                        <td>{row.language || "—"}</td>
                        <td><Badge>{row.status || "queue"}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </section>
      )}
    </>
  );
}
