import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";

type Severity = "success" | "info" | "error";
// An optional button on the message, e.g. "View" after an offer is accepted.
type Action = { label: string; onClick: () => void };
type Message = { key: number; text: string; severity: Severity; action?: Action };
type Feedback = {
  success: (text: string, action?: Action) => void;
  info: (text: string, action?: Action) => void;
  error: (text: string) => void;
};

const FeedbackContext = createContext<Feedback | null>(null);

// One place every screen confirms what just happened ("Deposit approved.").
// A snackbar rather than an inline alert: it shows wherever the user is on a
// long page, and screen readers announce it (role="status"/"alert").
// Results that are the page's content (e.g. "check your email") stay inline.
export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<Message | null>(null);
  const [open, setOpen] = useState(false);

  const show = useCallback((text: string, severity: Severity, action?: Action) => {
    setMessage({ key: Date.now(), text, severity, action });
    setOpen(true);
  }, []);

  const api = useMemo<Feedback>(
    () => ({
      success: (text, action) => show(text, "success", action),
      info: (text, action) => show(text, "info", action),
      error: (text) => show(text, "error"),
    }),
    [show],
  );

  return (
    <FeedbackContext.Provider value={api}>
      {children}
      <Snackbar
        key={message?.key}
        open={open}
        // errors stay until dismissed; confirmations go after a few seconds
        autoHideDuration={message?.severity === "error" ? null : 5000}
        onClose={(_, reason) => reason !== "clickaway" && setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        sx={{ bottom: { xs: 16, sm: 24 } }}
      >
        <Alert
          variant="filled"
          severity={message?.severity ?? "success"}
          onClose={() => setOpen(false)}
          role={message?.severity === "error" ? "alert" : "status"}
          action={
            message?.action ? (
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  setOpen(false);
                  message.action?.onClick();
                }}
              >
                {message.action.label}
              </Button>
            ) : undefined
          }
          sx={{ width: "100%", maxWidth: 560, alignItems: "center" }}
        >
          {message?.text}
        </Alert>
      </Snackbar>
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): Feedback {
  const ctx = useContext(FeedbackContext);
  if (!ctx) throw new Error("useFeedback must be used inside <FeedbackProvider>");
  return ctx;
}
