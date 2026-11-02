import { useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { useAuth } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";
import { ApiError } from "../api/client";
import type { CodeChallenge } from "../api/types";
import { BRAND } from "../brand";
import { SignInCodeStep } from "./SignInCodeStep";

// No self-registration: staff, principal officers and members are invited
// and set their password from the emailed link. Portal users then enter the
// one-time code emailed at every sign-in.
export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [challenge, setChallenge] = useState<CodeChallenge | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const needsCode = await login(email, password);
      if (needsCode) {
        setPassword("");
        setChallenge(needsCode);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (challenge) return <SignInCodeStep challenge={challenge} onCancel={() => setChallenge(null)} />;

  return (
    <AuthLayout onSubmit={handleSubmit}>
      <Typography variant="body2" color="text.secondary">
        Sign in to view and manage pension savings — for members, principal officers and administration staff.
      </Typography>
      <TextField
        label="Email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        fullWidth
      />
      <TextField
        label="Password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        fullWidth
      />
      {error && <Alert severity="error">{error}</Alert>}
      <Button type="submit" variant="contained" size="large" disabled={submitting} fullWidth>
        {submitting ? "Signing in…" : "Sign in"}
      </Button>
      <Link component={RouterLink} to="/forgot-password" variant="body2" sx={{ alignSelf: "center", py: 1 }}>
        Forgot your password?
      </Link>
      <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
        No account yet? Your employer's principal officer or {BRAND.administrator} will send you an invitation.
      </Typography>
    </AuthLayout>
  );
}
