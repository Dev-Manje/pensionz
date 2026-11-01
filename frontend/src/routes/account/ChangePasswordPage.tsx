import { useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { changePassword } from "../../api/auth";
import { ApiError, setTokens } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { NewPasswordFields, newPasswordProblem } from "../../auth/NewPasswordFields";

// /account/password — any signed-in user. Other sessions are signed out;
// this one carries on with the fresh tokens the server returns.
export function ChangePasswordPage() {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const problem = newPasswordProblem(password, confirm);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (problem || password !== confirm) return;
    setError(null);
    setDone(false);
    setSubmitting(true);
    try {
      setTokens(await changePassword(current, password));
      setCurrent("");
      setPassword("");
      setConfirm("");
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Stack sx={{ maxWidth: 520 }}>
      <PageHeader
        title="Change password"
        description="You'll stay signed in here; any other device or browser you're signed in on will be signed out."
      />
      <Paper variant="outlined" component="form" onSubmit={handleSubmit} sx={{ p: { xs: 2, sm: 3 } }}>
        <Stack spacing={2}>
          <TextField
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            fullWidth
          />
          <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
          {error && <Alert severity="error">{error}</Alert>}
          {done && <Alert severity="success">Password changed. We've also sent you an email to confirm it.</Alert>}
          <Button
            type="submit"
            variant="contained"
            disabled={submitting || !current || !!problem || password !== confirm}
            sx={{ alignSelf: { sm: "flex-start" } }}
          >
            {submitting ? "Saving…" : "Change password"}
          </Button>
        </Stack>
      </Paper>
    </Stack>
  );
}
