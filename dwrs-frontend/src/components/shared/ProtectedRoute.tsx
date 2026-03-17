/**
 * ProtectedRoute — RBAC route guard for React Router v6.
 * Redirects to login if not authenticated, or to /unauthorized if wrong role.
 */

import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAppSelector } from "../../app/store";

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles: string[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  allowedRoles,
}) => {
  const location = useLocation();
  const { isAuthenticated, user } = useAppSelector((state) => state.auth);

  if (!isAuthenticated) {
    // Redirect to login, preserving the attempted URL
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (!allowedRoles.includes(user?.role ?? "")) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
