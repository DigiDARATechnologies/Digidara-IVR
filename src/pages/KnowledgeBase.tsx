import { AlertCircle, BookOpen, CheckCircle2, Plus, Search, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { useAddDocument, useDeleteDocument, useKBDocuments, useKBSearch, useKBStatus } from "../api/knowledgeBase";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import { isDigidaraWorkspace } from "../utils/workspace";
import "./KnowledgeBase.css";

const COLLECTIONS = ["company", "courses", "internships", "services", "products", "career", "contact", "enrollment", "pricing", "founder", "case_studies", "policies"];

export function KnowledgeBase() {
  const allowed = isDigidaraWorkspace();

  // Hooks must run unconditionally on every render (Rules of Hooks) — the
  // workspace check below only affects what gets rendered, and `enabled`
  // flags keep a blocked workspace from firing (or endlessly retrying)
  // requests to an API it will only ever get a 403 from.
  const status = useKBStatus(allowed);
  const [activeCollection, setActiveCollection] = useState("faq");
  const [addOpen, setAddOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [liveSearch, setLiveSearch] = useState("");
  const [form, setForm] = useState({ doc_id: "", text: "" });

  const docs = useKBDocuments(activeCollection, allowed);
  const addDoc = useAddDocument();
  const deleteDoc = useDeleteDocument();
  const searchResults = useKBSearch(liveSearch, activeCollection || undefined);

  if (!allowed) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1 className="text-2xl font-extrabold">Knowledge Base</h1>
          </div>
        </div>
        <Card className="flex items-center gap-4 border-amber-100 bg-amber-50">
          <ShieldAlert className="text-amber-600" size={28} />
          <div>
            <p className="font-bold text-slate-900">Not available for your workspace</p>
            <p className="text-sm text-slate-500">
              This page manages DigiDARA's own dashboard content. To manage what your own AI agent uses on
              your live calls, use "My Knowledge Base" instead.
            </p>
          </div>
        </Card>
      </>
    );
  }

  async function handleAdd() {
    if (!form.doc_id.trim() || !form.text.trim()) {
      toast.error("Document ID and text are required.");
      return;
    }
    try {
      const result = await addDoc.mutateAsync({ collection: activeCollection, doc_id: form.doc_id.trim(), text: form.text.trim() });
      toast.success(`Added ${result.chunks_inserted} chunk(s) to ${activeCollection}.`);
      setForm({ doc_id: "", text: "" });
      setAddOpen(false);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function handleDelete(collection: string, doc_id: string) {
    if (!confirm(`Delete "${doc_id}" from ${collection}?`)) return;
    try {
      await deleteDoc.mutateAsync({ collection, doc_id });
      toast.success("Document deleted.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  const isAvailable = status.data?.available;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="text-2xl font-extrabold">Knowledge Base</h1>
          <p className="text-sm text-slate-500">Manage DigiDara AI RAG content — the assistant answers only from this knowledge.</p>
        </div>
        <Button onClick={() => setAddOpen(true)} disabled={!isAvailable}>
          <Plus size={16} /> Add document
        </Button>
      </div>

      {/* RAG status card */}
      <Card className={`mb-6 flex items-center gap-4 ${isAvailable ? "border-emerald-100 bg-emerald-50" : "border-amber-100 bg-amber-50"}`}>
        {status.isLoading ? (
          <Skeleton className="h-8 w-8 rounded-full" />
        ) : isAvailable ? (
          <CheckCircle2 className="text-emerald-600" size={28} />
        ) : (
          <AlertCircle className="text-amber-600" size={28} />
        )}
        <div>
          <p className="font-bold text-slate-900">
            {status.isLoading ? "Checking RAG status…" : isAvailable ? "RAG knowledge base is active" : "RAG knowledge base is unavailable"}
          </p>
          <p className="text-sm text-slate-500">
            {isAvailable
              ? `${status.data?.collections?.length || 0} collections loaded — the AI assistant uses this content to ground its answers.`
              : `The embedding model may still be downloading. ${status.data?.error ? `Error: ${status.data.error}` : ""}`}
          </p>
        </div>
      </Card>

      <div className="kb-grid">
        {/* Collection sidebar */}
        <Card>
          <p className="label mb-3">Collections</p>
          <nav className="kb-nav">
            {COLLECTIONS.map((col) => (
              <button
                key={col}
                className={`kb-nav-item ${activeCollection === col ? "kb-nav-item-active" : ""}`}
                onClick={() => setActiveCollection(col)}
              >
                <BookOpen size={14} />
                {col}
              </button>
            ))}
          </nav>
        </Card>

        {/* Main content area */}
        <div className="space-y-4">
          {/* Search */}
          <Card>
            <p className="label mb-2">Test retrieval — what would the AI find for this query?</p>
            <div className="flex gap-2">
              <input
                className="field flex-1"
                placeholder="Type a question like a customer would ask…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && setLiveSearch(searchQuery)}
              />
              <Button onClick={() => setLiveSearch(searchQuery)} disabled={!isAvailable}>
                <Search size={16} /> Test
              </Button>
            </div>
            {liveSearch && searchResults.data && (
              <div className="mt-4 space-y-2">
                <p className="label">{searchResults.data.chunks_found} chunk(s) retrieved:</p>
                {searchResults.data.chunks?.map((chunk: any, i: number) => (
                  <div key={i} className="kb-chunk">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge tone="gray">{chunk.collection}</Badge>
                      <span className="text-xs text-slate-400">distance: {chunk.distance}</span>
                    </div>
                    <p className="text-sm text-slate-700">{chunk.text}</p>
                  </div>
                ))}
                {searchResults.data.chunks_found === 0 && (
                  <p className="text-sm text-slate-400">No relevant chunks found — consider adding content about this topic.</p>
                )}
              </div>
            )}
          </Card>

          {/* Documents in collection */}
          <Card>
            <p className="label mb-3">Documents in "{activeCollection}"</p>
            {docs.isLoading ? (
              <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-12" />)}</div>
            ) : !isAvailable ? (
              <p className="text-sm text-amber-700">Knowledge base not yet available. Check the status card above.</p>
            ) : !docs.data?.length ? (
              <p className="text-sm text-slate-400">No documents in this collection yet. Click "Add document" to add content.</p>
            ) : (
              <div className="space-y-2">
                {docs.data.map((doc) => (
                  <div key={doc.id} className="kb-doc-row">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-slate-900 truncate">{doc.id}</p>
                      <p className="text-xs text-slate-500 line-clamp-1">{doc.preview}</p>
                    </div>
                    <button className="icon-btn flex-shrink-0" title="Delete" onClick={() => handleDelete(activeCollection, doc.id)}>
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Add document modal */}
      <Modal title={`Add document to "${activeCollection}"`} open={addOpen} onClose={() => setAddOpen(false)}>
        <div className="space-y-4">
          <label>
            <span className="label">Document ID <span className="text-slate-400">(slug, e.g. faq_pricing_2025)</span></span>
            <input className="field" placeholder="faq_pricing_2025" value={form.doc_id} onChange={(e) => setForm(f => ({ ...f, doc_id: e.target.value }))} />
          </label>
          <label>
            <span className="label">Content</span>
            <textarea
              className="field h-40 resize-y"
              placeholder="Paste the full document text here. It will be automatically chunked and embedded…"
              value={form.text}
              onChange={(e) => setForm(f => ({ ...f, text: e.target.value }))}
            />
            <span className="text-xs text-slate-400">{form.text.length} characters</span>
          </label>
          <Button onClick={handleAdd} disabled={addDoc.isPending} className="w-full">
            <Plus size={16} /> {addDoc.isPending ? "Saving…" : "Save to knowledge base"}
          </Button>
        </div>
      </Modal>
    </>
  );
}
