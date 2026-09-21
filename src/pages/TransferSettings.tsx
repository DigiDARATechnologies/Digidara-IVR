import { FormEvent, useState } from "react";
import { Building2, Pencil, PhoneForwarded, Plus, Radio, Trash2, Users, X } from "lucide-react";
import toast from "react-hot-toast";
import { getErrorMessage } from "../api/client";
import {
  useCreateDepartment,
  useCreateTransferDestination,
  useDeleteDepartment,
  useDeleteTransferDestination,
  useDepartments,
  useTransferDestinations,
  useUpdateDepartment,
  useUpdateTransferDestination,
} from "../api/transfers";
import type { Department, StaffDestination } from "../types";

const blankEdit = { name: "", phone_e164: "", department: "", priority: 100 };

export function TransferSettings() {
  const departments = useDepartments();
  const createDept = useCreateDepartment();
  const updateDept = useUpdateDepartment();
  const deleteDept = useDeleteDepartment();

  const destinations = useTransferDestinations();
  const create = useCreateTransferDestination();
  const update = useUpdateTransferDestination();
  const remove = useDeleteTransferDestination();

  const [deptForm, setDeptForm] = useState({ name: "", description: "" });
  const [editingDeptId, setEditingDeptId] = useState<number | null>(null);
  const [editDeptName, setEditDeptName] = useState("");

  const [form, setForm] = useState({ name: "", phone_e164: "", department: "", priority: 100 });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState(blankEdit);

  async function submitDept(event: FormEvent) {
    event.preventDefault();
    if (!deptForm.name.trim()) return;
    try {
      await createDept.mutateAsync(deptForm);
      setDeptForm({ name: "", description: "" });
      toast.success("Department created successfully.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function removeDept(dept: Department) {
    if (!confirm(`Delete department "${dept.name}"? Team members assigned to this department will become unassigned.`)) return;
    try {
      await deleteDept.mutateAsync(dept.id);
      toast.success("Department removed.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function saveDeptEdit(id: number) {
    if (!editDeptName.trim()) return;
    try {
      await updateDept.mutateAsync({ id, changes: { name: editDeptName } });
      toast.success("Department updated.");
      setEditingDeptId(null);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await create.mutateAsync(form);
      setForm({ name: "", phone_e164: "", department: "", priority: 100 });
      toast.success("Transfer destination added.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function toggle(id: number, is_active: boolean) {
    try {
      await update.mutateAsync({ id, changes: { is_active: !is_active } });
      toast.success(is_active ? "Destination disabled." : "Destination enabled.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  function startEdit(item: StaffDestination) {
    setEditingId(item.id);
    setEditForm({ name: item.name, phone_e164: item.phone_e164, department: item.department || "", priority: item.priority });
  }

  async function saveEdit(id: number) {
    try {
      await update.mutateAsync({ id, changes: editForm });
      toast.success("Destination updated.");
      setEditingId(null);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function removeDestination(id: number, name: string) {
    if (!confirm(`Remove "${name}"? This cannot be undone.`)) return;
    try {
      await remove.mutateAsync(id);
      toast.success("Destination removed.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  // Count active members per department for hunt group status
  const departmentMemberCounts = new Map<string, number>();
  (destinations.data || []).forEach(d => {
    if (d.is_active && d.department) {
      const key = d.department.trim().toLowerCase();
      departmentMemberCounts.set(key, (departmentMemberCounts.get(key) || 0) + 1);
    }
  });

  return <>
    <div className="page-heading">
      <div>
        <h1>Human Transfer & Team Hunt Groups</h1>
        <p>Manage dynamic departments and verified team member numbers for simultaneous ringing and live handoffs.</p>
      </div>
    </div>

    {/* Section 1: Department Management */}
    <section className="two-col mb-6">
      <form className="panel form-grid" onSubmit={submitDept}>
        <h2><Building2 size={20}/> Add Department</h2>
        <p className="text-sm text-slate-500">Create team departments (e.g., Business, Sales, Education) to route calls.</p>
        <label>
          Department Name
          <input
            required
            minLength={2}
            value={deptForm.name}
            onChange={e => setDeptForm({ ...deptForm, name: e.target.value })}
            placeholder="e.g. Sales, Business, Education"
          />
        </label>
        <label>
          Description (Optional)
          <input
            value={deptForm.description}
            onChange={e => setDeptForm({ ...deptForm, description: e.target.value })}
            placeholder="Inbound lead qualification team"
          />
        </label>
        <button className="accent-btn" disabled={createDept.isPending}>
          <Plus size={16}/>{createDept.isPending ? "Creating…" : "Add Department"}
        </button>
      </form>

      <article className="panel">
        <h2><Users size={20}/> Active Departments ({departments.data?.length || 0})</h2>
        {departments.isLoading ? (
          <p>Loading departments…</p>
        ) : departments.isError ? (
          <p>{getErrorMessage(departments.error)}</p>
        ) : departments.data?.length ? (
          <div className="call-list">
            {departments.data.map(dept => (
              editingDeptId === dept.id ? (
                <div className="flex items-center gap-2" key={dept.id}>
                  <input
                    value={editDeptName}
                    onChange={e => setEditDeptName(e.target.value)}
                    className="flex-1"
                    placeholder="Department name"
                  />
                  <button
                    type="button"
                    className="text-green-600"
                    disabled={updateDept.isPending}
                    onClick={() => saveDeptEdit(dept.id)}
                  >
                    <Pencil size={18}/>
                  </button>
                  <button type="button" onClick={() => setEditingDeptId(null)}>
                    <X size={18}/>
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2" key={dept.id}>
                  <div className="flex-1">
                    <span className="font-semibold text-slate-800">{dept.name}</span>
                    {dept.description && <small className="block text-slate-500">{dept.description}</small>}
                  </div>
                  <span className={`status-chip ${dept.member_count > 1 ? "bg-purple-100 text-purple-800" : ""}`}>
                    {dept.member_count} {dept.member_count === 1 ? "member" : "members"}
                    {dept.member_count > 1 && " · Hunt Group"}
                  </span>
                  <button
                    type="button"
                    aria-label="Edit department"
                    onClick={() => { setEditingDeptId(dept.id); setEditDeptName(dept.name); }}
                  >
                    <Pencil size={16}/>
                  </button>
                  <button
                    type="button"
                    className="text-red-600"
                    aria-label="Delete department"
                    disabled={deleteDept.isPending}
                    onClick={() => removeDept(dept)}
                  >
                    <Trash2 size={16}/>
                  </button>
                </div>
              )
            ))}
          </div>
        ) : (
          <p>No departments added yet. Create departments above.</p>
        )}
      </article>
    </section>

    {/* Section 2: Team Members / Staff Destinations */}
    <section className="two-col">
      <form className="panel form-grid" onSubmit={submit}>
        <h2><PhoneForwarded size={20}/> Add Team Member</h2>
        <label>
          Staff Name
          <input
            required
            minLength={2}
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            placeholder="John Doe"
          />
        </label>
        <label>
          Phone (E.164)
          <input
            required
            value={form.phone_e164}
            onChange={e => setForm({ ...form, phone_e164: e.target.value })}
            placeholder="+919876543210"
          />
        </label>
        <label>
          Department
          <select
            value={form.department}
            onChange={e => setForm({ ...form, department: e.target.value })}
          >
            <option value="">Select a department…</option>
            {departments.data?.map(dept => (
              <option key={dept.id} value={dept.name}>{dept.name}</option>
            ))}
          </select>
        </label>
        <label>
          Routing Priority
          <input
            type="number"
            min={1}
            max={9999}
            value={form.priority}
            onChange={e => setForm({ ...form, priority: Number(e.target.value) })}
          />
        </label>
        <button className="accent-btn" disabled={create.isPending}>
          <Plus size={16}/>{create.isPending ? "Saving…" : "Add Team Member"}
        </button>
      </form>

      <article className="panel">
        <h2>Configured Team Members</h2>
        {destinations.isLoading ? (
          <p>Loading…</p>
        ) : destinations.isError ? (
          <p>{getErrorMessage(destinations.error)}</p>
        ) : destinations.data?.length ? (
          <div className="call-list">
            {destinations.data.map(item => (
              editingId === item.id ? (
                <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_90px_42px_42px]" key={item.id}>
                  <label>Name<input required minLength={2} value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })}/></label>
                  <label>Phone<input required value={editForm.phone_e164} onChange={e => setEditForm({ ...editForm, phone_e164: e.target.value })}/></label>
                  <label>
                    Department
                    <select value={editForm.department} onChange={e => setEditForm({ ...editForm, department: e.target.value })}>
                      <option value="">None</option>
                      {departments.data?.map(dept => (
                        <option key={dept.id} value={dept.name}>{dept.name}</option>
                      ))}
                    </select>
                  </label>
                  <label>Priority<input type="number" min={1} max={9999} value={editForm.priority} onChange={e => setEditForm({ ...editForm, priority: Number(e.target.value) })}/></label>
                  <button className="mt-6 text-green-600" type="button" aria-label="Save" disabled={update.isPending} onClick={() => saveEdit(item.id)}><Pencil size={18}/></button>
                  <button className="mt-6" type="button" aria-label="Cancel" onClick={() => setEditingId(null)}><X size={18}/></button>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2" key={item.id}>
                  <button type="button" className="flex-1 text-left" onClick={() => toggle(item.id, item.is_active)}>
                    <span>
                      <b>{item.name}</b>
                      <small>{item.department || "General"} · {item.phone_e164}</small>
                    </span>
                    <span className="status-chip">{item.is_active ? "Active" : "Disabled"}</span>
                    {item.department && (departmentMemberCounts.get(item.department.trim().toLowerCase()) || 0) > 1 && (
                      <span className="status-chip bg-blue-100 text-blue-800" title="Simultaneous ring will ring all active members in this department">
                        <Radio size={12} className="inline mr-1"/>Simultaneous Ring
                      </span>
                    )}
                  </button>
                  <button type="button" aria-label="Edit destination" onClick={() => startEdit(item)}><Pencil size={16}/></button>
                  <button type="button" className="text-red-600" aria-label="Remove destination" disabled={remove.isPending} onClick={() => removeDestination(item.id, item.name)}><Trash2 size={16}/></button>
                </div>
              )
            ))}
          </div>
        ) : (
          <p>No team members configured yet.</p>
        )}
        <div className="mt-4 p-3 bg-slate-50 border border-slate-200 rounded text-sm text-slate-600">
          <p className="font-semibold text-slate-800 mb-1">⚡ Team Hunt Group (Simultaneous Ringing):</p>
          <p>When a call is transferred to a department (Business, Sales, Education, etc.), all active team members in that department receive the call simultaneously. The first person to answer and press 1 is connected, and all other ringing calls are automatically cancelled.</p>
        </div>
      </article>
    </section>
  </>;
}

