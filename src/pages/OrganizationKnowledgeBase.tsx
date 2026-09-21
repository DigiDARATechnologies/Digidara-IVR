import { Phone, Plus, Trash2, UploadCloud } from "lucide-react";
import { ChangeEvent, useState } from "react";
import toast from "react-hot-toast";
import {
  useAddOrgDocument,
  useDeleteOrgDocument,
  useOrgKBDocuments,
} from "../api/organizationKnowledgeBase";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import "./OrganizationKnowledgeBase.css";

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "ta", label: "Tamil" },
];

export function OrganizationKnowledgeBase() {
  const documents = useOrgKBDocuments();
  const addDocument = useAddOrgDocument();
  const deleteDocument = useDeleteOrgDocument();
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ collection: "", doc_id: "", text: "", lang: "en" });
  const [file, setFile] = useState<File | null>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] || null);
  }

  async function handleAdd() {
    if (!form.collection.trim() || !form.doc_id.trim()) {
      toast.error("Collection and document ID are required.");
      return;
    }
    if (!form.text.trim() && !file) {
      toast.error("Paste some text, upload a file, or both.");
      return;
    }
    try {
      const result = await addDocument.mutateAsync({
        collection: form.collection.trim(),
        doc_id: form.doc_id.trim(),
        text: form.text.trim(),
        lang: form.lang,
        file,
      });
      toast.success(`Added ${result.chunks_inserted} chunk(s) — your live calls will use this immediately.`);
      setForm({ collection: "", doc_id: "", text: "", lang: "en" });
      setFile(null);
      setAddOpen(false);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function handleDelete(docId: string) {
    if (!confirm(`Delete "${docId}" from your knowledge base?`)) return;
    try {
      await deleteDocument.mutateAsync(docId);
      toast.success("Document deleted.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">My Knowledge Base</h1>
          <p className="text-sm text-slate-500">
            Content only your organization's live calls use — merged on top of the shared baseline, never
            visible to other organizations.
          </p>
        </div>
        <Button onClick={() => setAddOpen(true)}>
          <Plus size={16} /> Add document
        </Button>
      </div>

      <Card className="mb-6 flex items-center gap-4 border-indigo-100 bg-indigo-50">
        <span className="rounded-lg bg-white p-3 text-indigo-600">
          <Phone size={20} />
        </span>
        <div>
          <p className="font-bold text-slate-900">Read live, on every call</p>
          <p className="text-sm text-slate-500">
            Anything added here is retrieved by your AI agent while it's actually talking to a customer — not a
            preview or a staged draft. Updates take effect on the very next call.
          </p>
        </div>
      </Card>

      <Card>
        <p className="label mb-3">Your documents</p>
        {documents.isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : !documents.data?.length ? (
          <p className="text-sm text-slate-400">
            No documents yet. Click "Add document" to give your AI agent business-specific content to draw on.
          </p>
        ) : (
          <div className="space-y-2">
            {documents.data.map((doc) => (
              <div key={doc.doc_id} className="org-kb-doc-row">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-slate-900 truncate">{doc.doc_id}</p>
                    <Badge tone="gray">{doc.collection}</Badge>
                    <Badge tone="blue">{doc.lang === "ta" ? "Tamil" : "English"}</Badge>
                  </div>
                  <p className="text-xs text-slate-500">
                    {doc.chunk_count} chunk{doc.chunk_count === 1 ? "" : "s"}
                    {doc.updated_at ? ` · updated ${doc.updated_at}` : ""}
                  </p>
                </div>
                <button
                  className="icon-btn flex-shrink-0"
                  title="Delete"
                  onClick={() => handleDelete(doc.doc_id)}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal title="Add document to your knowledge base" open={addOpen} onClose={() => setAddOpen(false)}>
        <div className="space-y-4">
          <label>
            <span className="label">Collection <span className="text-slate-400">(a topic label, e.g. pricing, faq, policies)</span></span>
            <input
              className="field"
              placeholder="pricing"
              value={form.collection}
              onChange={(event) => setForm((f) => ({ ...f, collection: event.target.value }))}
            />
          </label>
          <label>
            <span className="label">Document ID <span className="text-slate-400">(slug, e.g. refund_policy)</span></span>
            <input
              className="field"
              placeholder="refund_policy"
              value={form.doc_id}
              onChange={(event) => setForm((f) => ({ ...f, doc_id: event.target.value }))}
            />
          </label>
          <label>
            <span className="label">Language</span>
            <select
              className="field"
              value={form.lang}
              onChange={(event) => setForm((f) => ({ ...f, lang: event.target.value }))}
            >
              {LANGUAGES.map((language) => (
                <option key={language.value} value={language.value}>
                  {language.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Upload a file <span className="text-slate-400">(.pdf, .docx, or .txt — optional)</span></span>
            <input className="field" type="file" accept=".pdf,.docx,.txt" onChange={handleFileChange} />
            {file && <span className="upload-filename">{file.name}</span>}
          </label>
          <label>
            <span className="label">Content <span className="text-slate-400">(optional if you uploaded a file above)</span></span>
            <textarea
              className="field h-40 resize-y"
              placeholder="Paste the document text here, or leave blank if you uploaded a file above. Either way it will be automatically chunked and indexed for retrieval…"
              value={form.text}
              onChange={(event) => setForm((f) => ({ ...f, text: event.target.value }))}
            />
            <span className="text-xs text-slate-400">{form.text.length} characters</span>
          </label>
          <Button onClick={handleAdd} disabled={addDocument.isPending} className="w-full">
            <UploadCloud size={16} /> {addDocument.isPending ? "Saving…" : "Save to my knowledge base"}
          </Button>
        </div>
      </Modal>
    </>
  );
}
