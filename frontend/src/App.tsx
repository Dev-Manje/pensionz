import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LoginPage } from "./auth/LoginPage";
import { ForgotPasswordPage } from "./auth/ForgotPasswordPage";
import { ResetPasswordPage } from "./auth/ResetPasswordPage";
import { RoleRouter, canOpen } from "./routes/RoleRouter";
import { LoadingState } from "./components/LoadingState";
import { AuthLayout } from "./auth/AuthLayout";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";

// Where to send the user after signing in: the page they were trying to
// open (passed as ?next=), never an external URL.
function safeNext(search: string) {
  const next = new URLSearchParams(search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function LoginRoute() {
  const { user } = useAuth();
  const location = useLocation();
  if (user) {
    const next = safeNext(location.search);
    return <Navigate to={canOpen(next, user.roles) ? next : "/"} replace />;
  }
  return <LoginPage />;
}

function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) {
    const here = location.pathname + location.search;
    return <Navigate to={here === "/" ? "/login" : `/login?next=${encodeURIComponent(here)}`} replace />;
  }
  return <RoleRouter />;
}

function Shell() {
  const { loading, unreachable, retry } = useAuth();
  if (loading) return <LoadingState />;
  if (unreachable) {
    return (
      <AuthLayout>
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={retry}>
              Try again
            </Button>
          }
        >
          We can't reach the server right now. Check your connection — you're still signed in.
        </Alert>
      </AuthLayout>
    );
  }
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      {/* Open whether or not someone is signed in: an emailed link can be opened anywhere. */}
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/*" element={<RequireAuth />} />
    </Routes>
  );
}

export function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
