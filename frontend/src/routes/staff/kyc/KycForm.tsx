import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepButton from "@mui/material/StepButton";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { saveKyc, submitKyc } from "../../../api/kyc";
import { useDeclaration, useKycAction } from "../../../queries/kyc";
import type { KycApplication } from "../../../api/types";
import { KycDocuments } from "./KycDocuments";
import { KycField } from "./KycField";
import { KYC_STEPS, isShown, setPath, type PeopleDef, type StepDef } from "./kycSchema";

type Data = Record<string, unknown>;

function FieldGrid({ step, data, onChange }: { step: StepDef; data: Data; onChange: (name: string, value: unknown) => void }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
      {step.fields!.filter((f) => isShown(f, data)).map((f) => (
        <Box key={f.name} sx={{ gridColumn: f.width === "full" || f.type === "pep" || f.type === "textarea" ? "1 / -1" : undefined }}>
          <KycField field={f} data={data} onChange={onChange} />
        </Box>
      ))}
    </Box>
  );
}

function People({ def, data, setData }: { def: PeopleDef; data: Data; setData: (d: Data) => void }) {
  const people = (Array.isArray(data[def.name]) ? data[def.name] : []) as Data[];
  const setPeople = (next: Data[]) => setData({ ...data, [def.name]: next });
  return (
    <Stack spacing={2}>
      <Typography color="text.secondary">{def.help}</Typography>
      {people.map((person, i) => (
        <Paper key={i} variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
            <Typography sx={{ fontWeight: 600 }}>
              {def.singular} {i + 1}
              {person.full_name ? ` — ${String(person.full_name)}` : ""}
            </Typography>
            <IconButton aria-label={`Remove ${def.singular.toLowerCase()} ${i + 1}`} onClick={() => setPeople(people.filter((_, j) => j !== i))}>
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Stack>
          <FieldGrid
            step={{ key: def.name, title: def.singular, fields: def.fields }}
            data={person}
            onChange={(name, value) => setPeople(people.map((p, j) => (j === i ? setPath(p, name, value) : p)))}
          />
        </Paper>
      ))}
      <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setPeople([...people, {}])} sx={{ alignSelf: "flex-start" }}>
        Add {def.singular.toLowerCase()}
      </Button>
    </Stack>
  );
}

function DeclarationStep({ app, onSubmitted }: { app: KycApplication; onSubmitted: () => void }) {
  const declaration = useDeclaration(app.client_type);
  const feedback = useFeedback();
  const submit = useKycAction((args: { versionId: string; name: string }) => submitKyc(app.id, args.versionId, args.name));
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    setError(null);
    try {
      await submit.mutateAsync({ versionId: declaration.data!.id, name });
      feedback.success(`${app.reference} submitted — compliance will review it.`);
      onSubmitted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't submit the application.");
    }
  }

  return (
    <Stack spacing={2}>
      {app.problems.length > 0 && (
        <Alert severity="warning">
          <Typography sx={{ fontWeight: 600, mb: 0.5 }}>Still to do before submitting:</Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {app.problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </Box>
        </Alert>
      )}
      {declaration.data && (
        <Paper variant="outlined" sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600, mb: 1 }}>
            {declaration.data.title} <Typography component="span" variant="caption" color="text.secondary">(version {declaration.data.version})</Typography>
          </Typography>
          <Typography sx={{ whiteSpace: "pre-line" }}>{declaration.data.body}</Typography>
        </Paper>
      )}
      <TextField
        label={app.client_type === "individual" ? "Your full name" : "Full name of the person signing"}
        value={name}
        onChange={(e) => setName(e.target.value)}
        sx={{ maxWidth: 480 }}
        helperText="Typed in full; recorded with the date, time and the declaration version."
      />
      <FormControlLabel control={<Checkbox checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />} label="I have read and accept this declaration." />
      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <Button variant="contained" size="large" onClick={send} disabled={!agreed || name.trim().length < 2 || app.problems.length > 0 || submit.isPending || !declaration.data}>
          {submit.isPending ? "Submitting…" : "Submit for review"}
        </Button>
      </Box>
    </Stack>
  );
}

// The KYC application form as a stepper (FR-ONB-007: saved as a draft at every
// step change, resumable later). Steps come from kycSchema.ts.
export function KycForm({ app, onSubmitted }: { app: KycApplication; onSubmitted: () => void }) {
  const steps = KYC_STEPS[app.client_type];
  const feedback = useFeedback();
  const narrow = useMediaQuery(useTheme().breakpoints.down("md"));
  const save = useKycAction((data: Data) => saveKyc(app.id, data));
  const [active, setActive] = useState(0);
  const [data, setData] = useState<Data>(app.data ?? {});
  const [dirty, setDirty] = useState(false);
  const step = steps[active];

  const change = (next: Data) => {
    setData(next);
    setDirty(true);
  };

  async function persist(): Promise<boolean> {
    if (!dirty) return true;
    try {
      await save.mutateAsync(data);
      setDirty(false);
      return true;
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't save the draft.");
      return false;
    }
  }

  async function go(index: number) {
    if (await persist()) {
      setActive(index);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  return (
    <Stack spacing={2}>
      {app.status === "returned" && app.review_note && (
        <Alert severity="warning">
          <strong>Returned by compliance:</strong> {app.review_note}
        </Alert>
      )}
      {narrow ? (
        <TextField select label={`Step ${active + 1} of ${steps.length}`} value={active} onChange={(e) => go(Number(e.target.value))}>
          {steps.map((s, i) => (
            <MenuItem key={s.key} value={i}>
              {i + 1}. {s.title}
            </MenuItem>
          ))}
        </TextField>
      ) : (
        <Stepper nonLinear activeStep={active} alternativeLabel>
          {steps.map((s, i) => (
            <Step key={s.key}>
              <StepButton onClick={() => go(i)}>{s.title}</StepButton>
            </Step>
          ))}
        </Stepper>
      )}
      <Paper component="section" sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="h6" component="h2" sx={{ mb: 0.5 }}>
          {step.title}
        </Typography>
        {step.description && (
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            {step.description}
          </Typography>
        )}
        <Box sx={{ mt: 2 }}>
          {step.fields && <FieldGrid step={step} data={data} onChange={(name, value) => change(setPath(data, name, value))} />}
          {step.people && <People def={step.people} data={data} setData={change} />}
          {step.special === "documents" && (dirty ? <Alert severity="info">Saving your answers…</Alert> : <KycDocuments app={app} mode="edit" />)}
          {step.special === "declaration" && <DeclarationStep app={app} onSubmitted={onSubmitted} />}
        </Box>
      </Paper>
      <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", pb: 2 }}>
        <Button onClick={() => go(active - 1)} disabled={active === 0 || save.isPending}>
          Back
        </Button>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={async () => (await persist()) && feedback.success("Draft saved — you can come back to it later.")} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save draft"}
          </Button>
          {active < steps.length - 1 && (
            <Button variant="contained" onClick={() => go(active + 1)} disabled={save.isPending}>
              Next
            </Button>
          )}
        </Stack>
      </Stack>
    </Stack>
  );
}
