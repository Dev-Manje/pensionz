import { useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { forgotPassword } from "../api/auth";
import { ApiError } from "../api/client";
import { AuthLayout } from "./AuthLayout";

// /forgot-password — emails a reset link. The answer is the same whether or
// not the address has an account, so nobody can use it to find accounts.
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout onSubmit={sent ? undefined : handleSubmit}>
      <Typography variant="h6" component="h1">
        Reset your password
      </Typography>
      {sent ? (
        <>
          <Alert severity="success" sx={{ overflowWrap: "anywhere" }}>
            If <b>{email}</b> has an account, we've emailed it a link to choose a new password. The link works once and
            expires in 1 hour.
          </Alert>
          <Typography variant="body2" color="text.secondary">
            Nothing arrived? Check your spam folder, or ask your relationship manager to send you a new link.
          </Typography>
        </>
      ) : (
        <>
          <Typography variant="body2" color="text.secondary">
            Enter the email you sign in with and we'll send you a link to choose a new password.
          </Typography>
          <TextField
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            fullWidth
            autoFocus
          />
          {error && <Alert severity="error">{error}</Alert>}
          <Button type="submit" variant="contained" size="large" disabled={submitting} fullWidth>
            {submitting ? "Sending…" : "Email me a reset link"}
          </Button>
        </>
      )}
      <Link component={RouterLink} to="/login" variant="body2" sx={{ alignSelf: "center", py: 1 }}>
        Back to sign in
      </Link>
    </AuthLayout>
  );
}
