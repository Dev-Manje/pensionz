import { useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { removeKycDocument, reviewKycDocument, uploadKycDocument, viewKycDocument } from "../../../api/kyc";
import { useKycAction } from "../../../queries/kyc";
import { formatDate, todayIso } from "../../../utils/date";
import type { KycApplication, KycSlot } from "../../../api/types";

const MAX_BYTES = 10 * 1024 * 1024;

function UploadForm({ app, slot, onDone }: { app: KycApplication; slot: KycSlot; onDone: () => void }) {
  const feedback = useFeedback();
  const upload = useKycAction((file: File) =>
    uploadKycDocument(app.id, { requirement: slot.key, doc_type: docType, doc_type_other: other || null, issue_date: issue || null, expiry_date: expiry || null }, file),
  );
  const [docType, setDocType] = useState(slot.document?.doc_type ?? slot.types[0]?.code ?? "");
  const [other, setOther] = useState("");
  const [issue, setIssue] = useState("");
  const [expiry, setExpiry] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const chosen = slot.types.find((t) => t.code === docType);

  async function send() {
    setError(null);
    if (!file) return setError("Choose the file to upload.");
    if (file.size > MAX_BYTES) return setError("The file is larger than 10 MB.");
    try {
      await upload.mutateAsync(file);
      feedback.success(`${slot.label} uploaded.`);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't upload the file.");
    }
  }

  return (
    <Stack spacing={1.5} sx={{ mt: 1.5 }}>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 1.5 }}>
        <TextField select size="small" label="Document" value={docType} onChange={(e) => setDocType(e.target.value)}>
          {slot.types.map((t) => (
            <MenuItem key={t.code} value={t.code}>
              {t.label}
            </MenuItem>
          ))}
        </TextField>
        {docType === "other" && <TextField size="small" label="What is the document?" value={other} onChange={(e) => setOther(e.target.value)} required />}
        {slot.issue_date && (
          <TextField
            size="small"
            label="Issue date"
            type="date"
            value={issue}
            onChange={(e) => setIssue(e.target.value)}
            required
            slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }}
            helperText={chosen?.max_age_months ? `Must be from the last ${chosen.max_age_months} months.` : undefined}
          />
        )}
        {slot.expiry_date && (
          <TextField size="small" label="Expiry date" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        )}
      </Box>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
        <input ref={input} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Button variant="outlined" startIcon={<UploadFileOutlinedIcon />} onClick={() => input.current?.click()}>
          {file ? "Change file" : "Choose file"}
        </Button>
        <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
          {file ? `${file.name} (${Math.ceil(file.size / 1024)} KB)` : "PDF, JPEG, PNG or WebP, up to 10 MB"}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" onClick={send} disabled={upload.isPending || !file}>
          {upload.isPending ? "Uploading…" : "Upload"}
        </Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );
}

function DocumentCard({ app, slot, mode }: { app: KycApplication; slot: KycSlot; mode: "edit" | "review" | "view" }) {
  const feedback = useFeedback();
  const [uploading, setUploading] = useState(!slot.document);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const remove = useKycAction((docId: string) => removeKycDocument(app.id, docId));
  const review = useKycAction((args: { accept: boolean; reason?: string }) => reviewKycDocument(app.id, slot.document!.id, args.accept, args.reason));
  const doc = slot.document;

  async function view() {
    try {
      await viewKycDocument(app.id, doc!.id);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't open the document.");
    }
  }

  async function decide(accept: boolean) {
    try {
      await review.mutateAsync({ accept, reason: accept ? undefined : reason });
      setRejecting(false);
      setReason("");
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't save the review.");
    }
  }

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", rowGap: 1 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600 }}>{slot.label}</Typography>
          {doc ? (
            <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
              {doc.doc_type === "other" ? doc.doc_type_other : doc.doc_type_label}
              {doc.issue_date && ` · issued ${formatDate(doc.issue_date)}`}
              {doc.expiry_date && ` · expires ${formatDate(doc.expiry_date)}`} · {doc.filename}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Not uploaded yet
            </Typography>
          )}
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          {doc && <StatusChip status={doc.review_status === "pending" ? "pending_review" : doc.review_status} />}
          {doc && (
            <Button size="small" onClick={view}>
              View
            </Button>
          )}
          {mode === "edit" && doc && !uploading && (
            <>
              <Button size="small" onClick={() => setUploading(true)}>
                Replace
              </Button>
              <Button size="small" color="error" onClick={() => remove.mutate(doc.id)} disabled={remove.isPending}>
                Remove
              </Button>
            </>
          )}
        </Stack>
      </Stack>
      {doc?.review_status === "rejected" && doc.review_reason && (
        <Alert severity="warning" sx={{ mt: 1.5 }}>
          Not accepted: {doc.review_reason}
        </Alert>
      )}
      {slot.problems.map((p) => (
        <Alert key={p} severity="warning" sx={{ mt: 1.5 }}>
          {p}
        </Alert>
      ))}
      {mode === "edit" && uploading && <UploadForm app={app} slot={slot} onDone={() => setUploading(false)} />}
      {mode === "review" && doc && (
        <Stack spacing={1.5} sx={{ mt: 1.5 }}>
          {rejecting ? (
            <>
              <TextField size="small" label="Why isn't it acceptable?" value={reason} onChange={(e) => setReason(e.target.value)} multiline fullWidth required />
              <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
                <Button onClick={() => setRejecting(false)}>Cancel</Button>
                <Button color="error" variant="contained" onClick={() => decide(false)} disabled={!reason.trim() || review.isPending}>
                  Reject document
                </Button>
              </Stack>
            </>
          ) : (
            <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
              <Button color="error" variant="outlined" onClick={() => setRejecting(true)} disabled={review.isPending}>
                Reject
              </Button>
              <Button variant="contained" onClick={() => decide(true)} disabled={review.isPending || doc.review_status === "accepted"}>
                {doc.review_status === "accepted" ? "Accepted" : "Accept"}
              </Button>
            </Stack>
          )}
        </Stack>
      )}
    </Paper>
  );
}

// The documents an application needs (one card each), for uploading,
// reviewing or just looking at, depending on `mode`.
export function KycDocuments({ app, mode }: { app: KycApplication; mode: "edit" | "review" | "view" }) {
  if (app.slots.length === 0) {
    return <Alert severity="info">Fill in the earlier steps first — the documents needed depend on them.</Alert>;
  }
  return (
    <Stack spacing={1.5}>
      {app.slots.map((slot) => (
        <DocumentCard key={slot.key + (slot.document?.id ?? "")} app={app} slot={slot} mode={mode} />
      ))}
    </Stack>
  );
}
