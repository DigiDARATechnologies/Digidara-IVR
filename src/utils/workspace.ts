// organizations.id=1 is seeded as a fixed row (see app/database/db.py
// init_db()) and is always DigiDARA's own workspace — never a customer's.
// Mirrors the same check enforced server-side in app/api/rag.py.
const DIGIDARA_ORGANIZATION_ID = 1;

export function isDigidaraWorkspace(): boolean {
  try {
    const user = JSON.parse(localStorage.getItem("digidara-user") || "{}") as { organization_id?: number };
    return user.organization_id === DIGIDARA_ORGANIZATION_ID;
  } catch {
    return false;
  }
}
