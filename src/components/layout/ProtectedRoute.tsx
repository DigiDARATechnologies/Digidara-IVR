import { Navigate, Outlet } from "react-router-dom";

export function ProtectedRoute() {
  const token=localStorage.getItem("digidara-token")||"";
  // Reject the retired mock `local-session` value; authenticated API routes
  // require a signed three-part server token.
  return token.split(".").length===3 ? <Outlet /> : <Navigate to="/login" replace />;
}
