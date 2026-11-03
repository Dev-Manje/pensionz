import { useEffect, useRef, useState, type ReactNode } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import type { Theme } from "@mui/material/styles";
import { sendRemitCode } from "../../api/po";

// Sending a schedule or a payment notice moves money, so the officer confirms it
// with a one-time code emailed to them. The code is asked for as the dialog opens;
// a refused request (e.g. a row with errors) doesn't use it up.
export function RemitCodeDialog({ title, children, confirmLabel, onConfirm, onClose }: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: (code: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const fullScreen = useMediaQuery((t: Theme) => t.breakpoints.down("sm"));
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const asked = useRef(false);

  async function send() {
    setError(null);
    try {
      setSentTo((await sendRemitCode()).sent_to);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the code.");
    }
  }

  useEffect(() => {
    // Once per opening (StrictMode runs effects twice in development).
    if (asked.current) return;
    asked.current = true;
    void send();
  }, []);

  async function confirm() {
    setError(null);
    setBusy(true);
    try {
      await onConfirm(code.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onClose={busy ? undefined : onClose} fullWidth maxWidth="xs" fullScreen={fullScreen}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          {children}
          <Typography color="text.secondary">
            {sentTo ? `We emailed a 6-digit code to ${sentTo}. Enter it to confirm.` : "Sending you a one-time code…"}
          </Typography>
          <TextField
            label="One-time code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            slotProps={{ htmlInput: { inputMode: "numeric", autoComplete: "one-time-code", maxLength: 6 } }}
            autoFocus
          />
          {error && <Alert severity="error">{error}</Alert>}
          <Button onClick={send} size="small" sx={{ alignSelf: "flex-start" }} disabled={busy}>
            Send a new code
          </Button>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" onClick={confirm} disabled={code.length !== 6 || busy}>
          {busy ? "Sending…" : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
