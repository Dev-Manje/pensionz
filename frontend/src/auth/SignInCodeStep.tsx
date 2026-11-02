import { useState, type FormEvent } from "react";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { resendSignInCode } from "../api/auth";
import { ApiError } from "../api/client";
import type { CodeChallenge } from "../api/types";
import { useAuth } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";

// Second sign-in step for portal users (FR-PRT-006): the 6-digit code emailed
// to them. Used after the password on the sign-in page and after choosing a
// password from an invitation or reset link.
export function SignInCodeStep({
  challenge,
  onSignedIn,
  onCancel,
}: {
  challenge: CodeChallenge;
  onSignedIn?: () => void;
  onCancel: () => void;
}) {
  const { completeSignIn } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const complete = /^\d{6}$/.test(code);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!complete) return;
    setError(null);
    setInfo(null);
    setSubmitting(true);
    try {
      await completeSignIn(challenge.challenge, code);
      onSignedIn?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  async function resend() {
    setError(null);
    setInfo(null);
    setResending(true);
    try {
      setInfo((await resendSignInCode(challenge.challenge)).detail);
      setCode("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send a new code. Please try again.");
    } finally {
      setResending(false);
    }
  }

  return (
    <AuthLayout onSubmit={handleSubmit}>
      <Typography variant="h6" component="h1">
        Enter your sign-in code
      </Typography>
      <Typography variant="body2" color="text.secondary">
        We've emailed a 6-digit code to <b>{challenge.sentTo}</b>. It works once, for 10 minutes. Never share it with anyone.
      </Typography>
      <TextField
        label="Code"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        autoComplete="one-time-code"
        autoFocus
        required
        fullWidth
        slotProps={{ htmlInput: { inputMode: "numeric", pattern: "[0-9]*", maxLength: 6, "aria-describedby": "code-help" } }}
        sx={{ "& input": { fontSize: "1.5rem", letterSpacing: "0.4em", fontVariantNumeric: "tabular-nums" } }}
        helperText={<span id="code-help">Check your spam folder if it hasn't arrived within a minute.</span>}
      />
      {error && <Alert severity="error">{error}</Alert>}
      {info && <Alert severity="success">{info}</Alert>}
      <Button type="submit" variant="contained" size="large" disabled={submitting || !complete} fullWidth>
        {submitting ? "Checking…" : "Sign in"}
      </Button>
      <Stack direction="row" sx={{ gap: 1, justifyContent: "space-between", flexWrap: "wrap" }}>
        <Link component="button" type="button" variant="body2" onClick={resend} disabled={resending} sx={{ py: 1 }}>
          {resending ? "Sending…" : "Send a new code"}
        </Link>
        <Link component="button" type="button" variant="body2" onClick={onCancel} sx={{ py: 1 }}>
          Use a different account
        </Link>
      </Stack>
    </AuthLayout>
  );
}
