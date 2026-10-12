import React, { Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LoadingScreen } from '../components/shared/LoadingScreen';
import { Toaster } from './components/ui/sonner';
import { ProtectedRoute } from './components/ProtectedRoute';

const LandingPage = React.lazy(() => import('./pages/LandingPage').then(module => ({ default: module.LandingPage })));
const AdvisorPortal = React.lazy(() => import('./pages/advisor/AdvisorPortal').then(module => ({ default: module.AdvisorPortal })));
const StudentPortal = React.lazy(() => import('./pages/student/StudentPortal').then(module => ({ default: module.StudentPortal })));
const CompleteRegistration = React.lazy(() => import('../pages/auth/CompleteRegistration').then(module => ({ default: module.CompleteRegistration })));
const SlipLab = React.lazy(() => import('./pages/lab/SlipLab').then(module => ({ default: module.SlipLab })));

// ── Role-gated route wrapper ─────────────────────────────────────────────────
function RoleRoute({
  children,
  allowedRole,
}: {
  children: React.ReactNode;
  allowedRole: 'student' | 'advisor' | 'admin';
}) {
  return <ProtectedRoute allowedRole={allowedRole}>{children}</ProtectedRoute>;
}

export default function App() {
  const { user, role, isLoading } = useAuth();

  if (isLoading) return <LoadingScreen />;

  return (
    <>
      <Toaster />
      <BrowserRouter>
        <Suspense fallback={<LoadingScreen />}>
          <main role="main" className="flex-1 min-h-screen w-full flex flex-col">
            <Routes>
              {/* ── Root / Login ────────────────────────────────────────────── */}
              {/* Both / and /login show LandingPage when unauthenticated or role unresolved. */}
              {/* Authenticated users with verified roles are redirected to their portal.     */}
              <Route
                path="/"
                element={
                  user && role === 'advisor' ? (
                    <Navigate to="/advisor" replace />
                  ) : user && role === 'student' ? (
                    <Navigate to="/student" replace />
                  ) : user && !role ? (
                    <Navigate to="/complete-registration" replace />
                  ) : (
                    <LandingPage />
                  )
                }
              />
              {/* /login kept as alias for backwards-compat links */}
              <Route path="/login" element={<Navigate to="/" replace />} />
              {/* /complete-registration route */}
              <Route path="/complete-registration" element={<CompleteRegistration />} />
              {/* /landing kept so deep-links still work */}
              <Route path="/landing" element={<LandingPage />} />

              {/* ── Student Portal ───────────────────────────────────────────── */}
              <Route
                path="/student"
                element={
                  <RoleRoute allowedRole="student">
                    <StudentPortal />
                  </RoleRoute>
                }
              />
              <Route
                path="/student/*"
                element={
                  <RoleRoute allowedRole="student">
                    <StudentPortal />
                  </RoleRoute>
                }
              />

              {/* ── Advisor Portal ───────────────────────────────────────────── */}
              <Route
                path="/advisor"
                element={
                  <RoleRoute allowedRole="advisor">
                    <AdvisorPortal />
                  </RoleRoute>
                }
              />
              <Route
                path="/advisor/*"
                element={
                  <RoleRoute allowedRole="advisor">
                    <AdvisorPortal />
                  </RoleRoute>
                }
              />

              {/* ── Staging Slip Lab ────────────────────────────────────────── */}
              {(import.meta.env.VITE_ENVIRONMENT === 'staging' || import.meta.env.MODE === 'staging') && (
                <Route path="/lab" element={<SlipLab />} />
              )}

              {/* ── Catch-All ───────────────────────────────────────────────── */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </Suspense>
      </BrowserRouter>
    </>
  );
}