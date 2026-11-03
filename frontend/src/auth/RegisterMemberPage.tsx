import { useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { apiFetch, ApiError } from "../api/client";
import type { TokenPair } from "../api/types";
import { BRAND } from "../brand";
import { useAuth } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";
import { NewPasswordFields, newPasswordProblem } from "./NewPasswordFields";

// /register — a member signs up for the portal (FR-PRT-006): member number + ID
// number + date of birth; a one-time code goes to the email on their record;
// the code and a new password finish it and sign them in.
export function RegisterMemberPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [memberNumber, setMemberNumber] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [born, setBorn] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await apiFetch<{ challenge: string; detail: string }>("/auth/member-register/start", {
        method: "POST",
        body: JSON.stringify({ member_number: memberNumber, id_number: idNumber, date_of_birth: born }),
      });
      setChallenge(r.challenge);
      setNotice(r.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function finish(e: FormEvent) {
    e.preventDefault();
    if (newPasswordProblem(password, confirm) || password !== confirm) return;
    setError(null);
    setBusy(true);
    try {
      const tokens = await apiFetch<TokenPair>("/auth/member-register/finish", {
        method: "POST",
        body: JSON.stringify({ challenge, code: code.trim(), new_password: password }),
      });
      await signIn(tokens);
      navigate("/member", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <AuthLayout>
      <Typography variant="h6" component="h1">
        Register for the member portal
      </Typography>
      {!challenge ? (
        <Stack component="form" spacing={2} onSubmit={start} sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Use the details on your membership record. We send a one-time code to the email address we hold for you.
          </Typography>
          <TextField label="Member number" value={memberNumber} onChange={(e) => setMemberNumber(e.target.value)} required autoComplete="off" />
          <TextField label="ID number" value={idNumber} onChange={(e) => setIdNumber(e.target.value)} required autoComplete="off" />
          <TextField label="Date of birth" type="date" value={born} onChange={(e) => setBorn(e.target.value)} required slotProps={{ inputLabel: { shrink: true } }} />
          {error && <Alert severity="error">{error}</Alert>}
          <Button type="submit" variant="contained" size="large" disabled={busy}>
            {busy ? "Checking…" : "Continue"}
          </Button>
        </Stack>
      ) : (
        <Stack component="form" spacing={2} onSubmit={finish} sx={{ mt: 2 }}>
          <Alert severity="info">{notice}</Alert>
          <TextField
            label="6-digit code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            required
            autoComplete="one-time-code"
            slotProps={{ htmlInput: { inputMode: "numeric", pattern: "\\d{6}" } }}
          />
          <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
          {error && <Alert severity="error">{error}</Alert>}
          <Button type="submit" variant="contained" size="large" disabled={busy || code.length !== 6}>
            {busy ? "Saving…" : "Create my login"}
          </Button>
          <Typography variant="body2" color="text.secondary">
            No code after a few minutes? Your email on record may be missing or out of date — contact {BRAND.administrator}.
          </Typography>
        </Stack>
      )}
      <Typography variant="body2" sx={{ mt: 2, textAlign: "center" }}>
        <Link component={RouterLink} to="/login">
          Back to sign in
        </Link>
      </Typography>
    </AuthLayout>
  );
}
