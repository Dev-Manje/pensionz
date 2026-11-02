import { useEffect, useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate, useSearchParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { getResetLinkStatus, resetPassword, type ResetLinkStatus } from "../api/auth";
import { ApiError } from "../api/client";
import { LoadingState } from "../components/LoadingState";
import { useAuth } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";
import { NewPasswordFields, newPasswordProblem } from "./NewPasswordFields";
import { SignInCodeStep } from "./SignInCodeStep";
import type { CodeChallenge } from "../api/types";

// /reset-password?token=… — from a "forgot password" email or a portal
// invitation (&welcome=1). Checks the link first, then sets the password
// and signs the user straight in (portal users after the emailed code).
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [link, setLink] = useState<ResetLinkStatus | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [challenge, setChallenge] = useState<CodeChallenge | null>(null);

  useEffect(() => {
    if (!token) {
      setLink({ valid: false, purpose: null, email: null });
      return;
    }
    getResetLinkStatus(token)
      .then(setLink)
      .catch(() => setLink({ valid: false, purpose: null, email: null }));
  }, [token]);

  const invite = link?.purpose === "invite";
  const problem = newPasswordProblem(password, confirm);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (problem || password !== confirm) return;
    setError(null);
    setSubmitting(true);
    try {
      const needsCode = await signIn(await resetPassword(token, password));
      if (needsCode) {
        setChallenge(needsCode);
        return;
      }
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  if (challenge) {
    // The password is saved; the link is used up, so "cancel" goes to sign-in.
    return (
      <SignInCodeStep
        challenge={challenge}
        onSignedIn={() => navigate("/", { replace: true })}
        onCancel={() => navigate("/login", { replace: true })}
      />
    );
  }

  if (link === null) return <LoadingState />;

  if (!link.valid) {
    return (
      <AuthLayout>
        <Typography variant="h6" component="h1">
          This link no longer works
        </Typography>
        <Alert severity="warning">
          Password links work once and expire after a while. Ask for a new one below, or contact your relationship
          manager.
        </Alert>
        <Button component={RouterLink} to="/forgot-password" variant="contained" size="large" fullWidth>
          Get a new link
        </Button>
        <Link component={RouterLink} to="/login" variant="body2" sx={{ alignSelf: "center", py: 1 }}>
          Back to sign in
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout onSubmit={handleSubmit}>
      <Typography variant="h6" component="h1">
        {invite ? "Welcome — set up your login" : "Choose a new password"}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {invite ? "Choose a password for " : "For "}
        <b>{link.email}</b>.{" "}
        {invite ? "You'll use it with this email to sign in." : "You'll be signed out everywhere else."}
      </Typography>
      <NewPasswordFields
        label="Password"
        password={password}
        confirm={confirm}
        onPassword={setPassword}
        onConfirm={setConfirm}
      />
      {error && <Alert severity="error">{error}</Alert>}
      <Button
        type="submit"
        variant="contained"
        size="large"
        disabled={submitting || !!problem || password !== confirm}
        fullWidth
      >
        {submitting ? "Saving…" : invite ? "Set password and sign in" : "Save password and sign in"}
      </Button>
    </AuthLayout>
  );
}
