import { Building2, CheckCircle2, Circle, FileCheck2, Loader2, PhoneCall, RefreshCw, Route, ShieldCheck } from "lucide-react";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  AvailableNumber,
  NUMBER_PREFIXES,
  useBuyNumber,
  useProvisioningStatus,
  useSearchNumbers,
  useSubmitCompliance,
} from "../api/provisioning";
import { useCampaigns } from "../api/campaigns";
import { usePhoneNumbers, useCreatePhoneNumber, useUpdatePhoneNumber } from "../api/phoneNumbers";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import "./PlivoProvisioning.css";

function digitsOnly(value: string): string {
  return value.replace(/\D/g, "");
}

function statusTone(status: string): "green" | "amber" | "red" | "gray" {
  const normalized = status.toLowerCase();
  if (normalized.includes("reject")) return "red";
  if (normalized.includes("accept") || normalized.includes("approv")) return "green";
  if (normalized === "not_started") return "gray";
  return "amber";
}

function BusinessDetailsForm({ onSubmitted, resubmitting }: { onSubmitted: () => void; resubmitting: boolean }) {
  const submit = useSubmitCompliance();
  const [fields, setFields] = useState({
    business_name: "",
    business_email: "",
    address_line1: "",
    city: "",
    state: "",
    postal_code: "",
    registration_number: "",
  });
  const [registrationCertificate, setRegistrationCertificate] = useState<File | null>(null);
  const [gstCertificate, setGstCertificate] = useState<File | null>(null);

  function setField(key: keyof typeof fields, value: string) {
    setFields((current) => ({ ...current, [key]: value }));
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>, setter: (file: File | null) => void) {
    setter(event.target.files?.[0] || null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!Object.values(fields).every((value) => value.trim())) {
      toast.error("Fill in every business detail field.");
      return;
    }
    if (!registrationCertificate || !gstCertificate) {
      toast.error("Upload both required documents.");
      return;
    }
    try {
      await submit.mutateAsync({
        ...fields,
        registrationCertificate,
        gstCertificate,
      });
      toast.success("Application submitted — Plivo is reviewing your documents.");
      onSubmitted();
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  return (
    <Card>
      <div className="mb-4 flex items-center gap-3">
        <div className="rounded-lg bg-indigo-50 p-3 text-indigo-600">
          <Building2 size={20} />
        </div>
        <div>
          <h2 className="text-lg font-bold">{resubmitting ? "Resubmit business details" : "Business details"}</h2>
          <p className="text-sm text-slate-500">
            Used to register your own dedicated calling number with Plivo. This is required once per business.
          </p>
        </div>
      </div>
      <form className="provisioning-form" onSubmit={handleSubmit}>
        <div className="provisioning-form-grid">
          <label>
            <span className="label">Business / entity name</span>
            <input
              className="field"
              value={fields.business_name}
              onChange={(event) => setField("business_name", event.target.value)}
              placeholder="Acme Private Limited"
            />
          </label>
          <label>
            <span className="label">Business email</span>
            <input
              className="field"
              type="email"
              value={fields.business_email}
              onChange={(event) => setField("business_email", event.target.value)}
              placeholder="ops@acme.in"
            />
          </label>
          <label className="provisioning-span-2">
            <span className="label">Registered address</span>
            <input
              className="field"
              value={fields.address_line1}
              onChange={(event) => setField("address_line1", event.target.value)}
              placeholder="1 MG Road"
            />
          </label>
          <label>
            <span className="label">City</span>
            <input
              className="field"
              value={fields.city}
              onChange={(event) => setField("city", event.target.value)}
              placeholder="Bangalore"
            />
          </label>
          <label>
            <span className="label">State</span>
            <input
              className="field"
              value={fields.state}
              onChange={(event) => setField("state", event.target.value)}
              placeholder="Karnataka"
            />
          </label>
          <label>
            <span className="label">Postal code</span>
            <input
              className="field"
              value={fields.postal_code}
              onChange={(event) => setField("postal_code", event.target.value)}
              placeholder="560001"
            />
          </label>
          <label>
            <span className="label">Registration number (CIN / Udyam)</span>
            <input
              className="field"
              value={fields.registration_number}
              onChange={(event) => setField("registration_number", event.target.value)}
              placeholder="U12345KA2020PTC000000"
            />
          </label>
        </div>

        <div className="provisioning-form-grid">
          <label>
            <span className="label">Business registration certificate</span>
            <input
              className="field"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={(event) => handleFile(event, setRegistrationCertificate)}
            />
            {registrationCertificate && <span className="upload-filename">{registrationCertificate.name}</span>}
          </label>
          <label>
            <span className="label">GST certificate</span>
            <input
              className="field"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={(event) => handleFile(event, setGstCertificate)}
            />
            {gstCertificate && <span className="upload-filename">{gstCertificate.name}</span>}
          </label>
        </div>

        <Button disabled={submit.isPending}>
          <FileCheck2 size={16} />
          {submit.isPending ? "Submitting…" : "Submit for approval"}
        </Button>
      </form>
    </Card>
  );
}

function PendingReview({ status }: { status: string }) {
  return (
    <Card>
      <div className="provisioning-pending">
        <Loader2 size={28} className="animate-spin text-indigo-600" />
        <div>
          <h2 className="text-lg font-bold">Plivo is reviewing your documents</h2>
          <p className="text-sm text-slate-500">
            This usually takes anywhere from 15 minutes to one business day. Current status: <Badge tone={statusTone(status)}>{status}</Badge>
          </p>
        </div>
      </div>
    </Card>
  );
}

function Rejected({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className="mb-6">
      <div className="mb-2 flex items-center gap-2 text-rose-600">
        <ShieldCheck size={18} />
        <h2 className="text-lg font-bold">Application rejected</h2>
      </div>
      <p className="text-sm text-slate-500">
        Plivo rejected the last submission. Double-check the documents and details below, then resubmit.
      </p>
      <Button variant="secondary" className="mt-4" onClick={onRetry}>
        Resubmit
      </Button>
    </Card>
  );
}

function NumberPicker({ complianceApplicationId }: { complianceApplicationId: string }) {
  const [selectedPrefix, setSelectedPrefix] = useState<string | null>(null);
  const [selectedNumber, setSelectedNumber] = useState<string | null>(null);
  const numbers = useSearchNumbers(selectedPrefix);
  const buyNumber = useBuyNumber();

  function choosePrefix(prefix: string) {
    setSelectedPrefix(prefix);
    setSelectedNumber(null);
  }

  async function confirmPurchase() {
    if (!selectedNumber) return;
    try {
      await buyNumber.mutateAsync({ number: selectedNumber, complianceApplicationId });
      toast.success(`${selectedNumber} is now your dedicated calling number.`);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  return (
    <>
      <Card className="mb-6">
        <div className="mb-3 flex items-center gap-2 text-emerald-600">
          <CheckCircle2 size={18} />
          <h2 className="text-lg font-bold">Approved — choose your number prefix</h2>
        </div>
        <p className="text-sm text-slate-500">
          This is about how likely people are to actually answer, not your city. Numbers starting with{" "}
          <strong>080</strong> or <strong>022</strong> read as real landlines, so people pick up. Numbers in other
          formats commonly get ignored or rejected as spam/telemarketing before the call is ever answered. Pick
          whichever prefix you want your calls to be recognized by — this choice is required.
        </p>
        <div className="prefix-choice">
          {NUMBER_PREFIXES.map(({ prefix }) => (
            <button
              key={prefix}
              type="button"
              className={`prefix-option ${selectedPrefix === prefix ? "active" : ""}`}
              onClick={() => choosePrefix(prefix)}
            >
              {selectedPrefix === prefix ? <CheckCircle2 size={16} /> : <Circle size={16} />}
              <span className="prefix-option-code">{prefix}</span>
              <span className="prefix-option-note">trusted landline-style prefix</span>
            </button>
          ))}
        </div>
      </Card>

      {selectedPrefix && (
        <Card>
          <h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">
            Available {selectedPrefix} numbers
          </h3>
          {numbers.isLoading ? (
            <p className="text-sm text-slate-500">Searching available numbers…</p>
          ) : !numbers.data?.length ? (
            <p className="text-sm text-slate-500">No numbers currently available for this prefix. Try again shortly.</p>
          ) : (
            <div className="number-list">
              {numbers.data.map((entry: AvailableNumber) => (
                <label key={entry.number} className={`number-option ${selectedNumber === entry.number ? "active" : ""}`}>
                  <input
                    type="radio"
                    name="chosen-number"
                    checked={selectedNumber === entry.number}
                    onChange={() => setSelectedNumber(entry.number)}
                  />
                  <span className="number-option-value">{entry.number}</span>
                  {entry.monthly_rental_rate && (
                    <span className="number-option-rate">₹{entry.monthly_rental_rate}/mo</span>
                  )}
                </label>
              ))}
            </div>
          )}
          <Button className="mt-4" disabled={!selectedNumber || buyNumber.isPending} onClick={confirmPurchase}>
            <PhoneCall size={16} />
            {buyNumber.isPending ? "Provisioning…" : selectedNumber ? `Use ${selectedNumber}` : "Choose a number"}
          </Button>
        </Card>
      )}
    </>
  );
}

function InboundRouting({ number }: { number: string }) {
  const normalizedNumber = digitsOnly(number);
  const campaigns = useCampaigns();
  const phoneNumbers = usePhoneNumbers();
  const createRoute = useCreatePhoneNumber();
  const updateRoute = useUpdatePhoneNumber();

  const existing = phoneNumbers.data?.find((entry) => entry.plivo_number === normalizedNumber);
  const [campaignId, setCampaignId] = useState<string>("");
  const [label, setLabel] = useState("");

  useEffect(() => {
    if (existing) {
      setCampaignId(String(existing.campaign_id));
      setLabel(existing.label || "");
    }
  }, [existing?.campaign_id, existing?.label]);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaignId) {
      toast.error("Choose which campaign should answer inbound calls to this number.");
      return;
    }
    try {
      if (existing) {
        await updateRoute.mutateAsync({
          id: existing.id,
          payload: { campaign_id: Number(campaignId), label: label || null },
        });
      } else {
        await createRoute.mutateAsync({
          plivo_number: normalizedNumber,
          campaign_id: Number(campaignId),
          label: label || null,
        });
      }
      toast.success("Inbound routing saved.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  const isSaving = createRoute.isPending || updateRoute.isPending;

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2 text-indigo-600">
        <Route size={18} />
        <h2 className="text-lg font-bold">Inbound call routing</h2>
      </div>
      <p className="mb-4 text-sm text-slate-500">
        Choose which campaign's AI receptionist answers calls customers make to <strong>{number}</strong>.
        {existing?.is_active === false && (
          <span className="text-rose-600"> Routing is currently disabled for this number.</span>
        )}
      </p>
      {campaigns.isLoading || phoneNumbers.isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : !campaigns.data?.length ? (
        <p className="text-sm text-slate-500">
          <Link to="/campaigns" className="font-semibold text-indigo-600 hover:underline">
            Create a campaign
          </Link>{" "}
          first, then come back here to route this number to it.
        </p>
      ) : (
        <form className="provisioning-form" onSubmit={handleSave}>
          <div className="provisioning-form-grid">
            <label>
              <span className="label">Campaign</span>
              <select
                className="field"
                value={campaignId}
                onChange={(event) => setCampaignId(event.target.value)}
              >
                <option value="">Select a campaign…</option>
                {campaigns.data.map((campaign) => (
                  <option key={campaign.id} value={campaign.id}>
                    {campaign.campaign_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="label">Label (optional)</span>
              <input
                className="field"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="Bangalore front desk"
              />
            </label>
          </div>
          <Button disabled={isSaving}>
            {isSaving ? "Saving…" : existing ? "Update routing" : "Enable inbound routing"}
          </Button>
        </form>
      )}
    </Card>
  );
}

function Provisioned({ number, subaccountAuthId }: { number: string; subaccountAuthId?: string | null }) {
  return (
    <>
      <Card className="mb-6">
        <div className="mb-2 flex items-center gap-2 text-emerald-600">
          <CheckCircle2 size={18} />
          <h2 className="text-lg font-bold">Your dedicated calling number is live</h2>
        </div>
        <p className="text-sm text-slate-500">
          Outbound calls now go out from <strong>{number}</strong>, billed under your own isolated Plivo subaccount
          {subaccountAuthId ? ` (${subaccountAuthId})` : ""}.
        </p>
      </Card>
      <InboundRouting number={number} />
    </>
  );
}

export function PlivoProvisioning() {
  const status = useProvisioningStatus();
  const [forceForm, setForceForm] = useState(false);

  if (status.isLoading) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1 className="text-2xl font-extrabold">Dedicated Calling Number</h1>
            <p className="text-sm text-slate-500">Provision your own Plivo number for outbound calls.</p>
          </div>
        </div>
        <Card>
          <p className="text-sm text-slate-500">Loading…</p>
        </Card>
      </>
    );
  }

  const data = status.data;
  const currentStatus = data?.status || "not_started";
  const showForm = forceForm || currentStatus === "not_started" || currentStatus === "rejected";

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Dedicated Calling Number</h1>
          <p className="text-sm text-slate-500">
            Provision your own Plivo number so outbound calls use your business identity and billing instead of the
            shared default.
          </p>
        </div>
        {data?.updated_at && (
          <Button variant="ghost" onClick={() => status.refetch()} disabled={status.isFetching}>
            <RefreshCw size={14} className={status.isFetching ? "animate-spin" : ""} />
            Refresh
          </Button>
        )}
      </div>

      {data?.provisioned_number ? (
        <Provisioned number={data.provisioned_number} subaccountAuthId={data.subaccount_auth_id} />
      ) : showForm ? (
        <>
          {currentStatus === "rejected" && !forceForm && <Rejected onRetry={() => setForceForm(true)} />}
          <BusinessDetailsForm resubmitting={currentStatus === "rejected"} onSubmitted={() => setForceForm(false)} />
        </>
      ) : currentStatus.toLowerCase().includes("accept") || currentStatus.toLowerCase().includes("approv") ? (
        data?.plivo_compliance_id ? (
          <NumberPicker complianceApplicationId={data.plivo_compliance_id} />
        ) : (
          <Card>
            <p className="text-sm text-slate-500">Approved, but the compliance reference is missing. Contact support.</p>
          </Card>
        )
      ) : (
        <PendingReview status={currentStatus} />
      )}
    </>
  );
}
