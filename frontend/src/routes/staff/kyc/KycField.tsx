import { useState } from "react";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormHelperText from "@mui/material/FormHelperText";
import FormLabel from "@mui/material/FormLabel";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useListRows } from "../../../queries/setup";
import { useKycOptions } from "../../../queries/kyc";
import type { ListRow } from "../../../api/types";
import { getPath, type FieldDef } from "./kycSchema";

interface Props {
  field: FieldDef;
  data: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}

const rowLabel = (r: ListRow) => String(r.name ?? r.code ?? "");

function YesNo({ field, value, onChange, children }: { field: FieldDef; value: unknown; onChange: (v: boolean) => void; children?: React.ReactNode }) {
  return (
    <FormControl required={field.required} component="fieldset">
      <FormLabel component="legend" sx={{ color: "text.primary", fontWeight: 500 }}>
        {field.label}
      </FormLabel>
      {children}
      <RadioGroup row value={value === true ? "yes" : value === false ? "no" : ""} onChange={(e) => onChange(e.target.value === "yes")}>
        <FormControlLabel value="yes" control={<Radio />} label="Yes" />
        <FormControlLabel value="no" control={<Radio />} label="No" />
      </RadioGroup>
      {field.help && <FormHelperText>{field.help}</FormHelperText>}
    </FormControl>
  );
}

function PepQuestion({ field, value, onChange }: { field: FieldDef; value: unknown; onChange: (v: boolean) => void }) {
  const options = useKycOptions();
  const [open, setOpen] = useState(false);
  return (
    <YesNo field={field} value={value} onChange={onChange}>
      <Typography variant="body2" sx={{ mt: 0.5 }}>
        <Box component="button" type="button" onClick={() => setOpen((o) => !o)} sx={{ p: 0, border: 0, background: "none", color: "primary.main", cursor: "pointer", textDecoration: "underline", font: "inherit" }}>
          {open ? "Hide" : "What is a politically exposed person?"}
        </Box>
      </Typography>
      {open && options.data && (
        <Alert severity="info" sx={{ mt: 1 }}>
          {options.data.pep_definition}
        </Alert>
      )}
    </YesNo>
  );
}

function ListField({ field, value, onChange, data, byId }: { field: FieldDef; value: unknown; onChange: (v: unknown) => void; data: Record<string, unknown>; byId: boolean }) {
  const parent = field.parentField ? (getPath(data, field.parentField) as string | null) : null;
  const rows = useListRows(field.list ?? null, parent);
  const options = (rows.data ?? []).filter((r) => r.active !== false);
  const key = (r: ListRow) => (byId ? r.id : String(r.code));
  const selected = options.find((r) => key(r) === value) ?? null;
  const waitingForParent = !!field.parentField && !parent;
  return (
    <Autocomplete
      options={options}
      value={selected}
      loading={rows.isLoading}
      disabled={waitingForParent}
      onChange={(_, row) => onChange(row ? key(row) : null)}
      getOptionLabel={rowLabel}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      renderInput={(params) => (
        <TextField
          {...params}
          label={field.label}
          required={field.required}
          helperText={waitingForParent ? "Choose the one above first." : field.help}
        />
      )}
    />
  );
}

function MultiListField({ field, value, onChange }: { field: FieldDef; value: unknown; onChange: (v: string[]) => void }) {
  const rows = useListRows(field.list ?? null);
  const options = (rows.data ?? []).filter((r) => r.active !== false);
  const codes = Array.isArray(value) ? (value as string[]) : [];
  return (
    <Autocomplete
      multiple
      options={options}
      value={options.filter((r) => codes.includes(String(r.code)))}
      onChange={(_, chosen) => onChange(chosen.map((r) => String(r.code)))}
      getOptionLabel={rowLabel}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      renderInput={(params) => <TextField {...params} label={field.label} helperText={field.help} />}
    />
  );
}

function TagsField({ field, value, onChange }: { field: FieldDef; value: unknown; onChange: (v: string[]) => void }) {
  const tags = Array.isArray(value) ? (value as string[]) : [];
  return (
    <Autocomplete
      multiple
      freeSolo
      options={[]}
      value={tags}
      // Comma-separated input is accepted too (FR-ONB-I02).
      onChange={(_, values) => onChange([...new Set(values.flatMap((v) => String(v).split(",")).map((v) => v.trim()).filter(Boolean))])}
      renderValue={(values, getItemProps) => values.map((v, i) => <Chip size="small" label={v} {...getItemProps({ index: i })} key={v} />)}
      renderInput={(params) => <TextField {...params} label={field.label} helperText={field.help} />}
    />
  );
}

// One KYC form field, by type (see kycSchema.ts).
export function KycField({ field, data, onChange }: Props) {
  const options = useKycOptions();
  const value = getPath(data, field.name);
  const set = (v: unknown) => onChange(field.name, v);
  switch (field.type) {
    case "yes_no":
      return <YesNo field={field} value={value} onChange={set} />;
    case "pep":
      return <PepQuestion field={field} value={value} onChange={set} />;
    case "list":
      return <ListField field={field} value={value} onChange={set} data={data} byId={false} />;
    case "place":
      return <ListField field={field} value={value} onChange={set} data={data} byId />;
    case "multi_list":
      return <MultiListField field={field} value={value} onChange={set} />;
    case "tags":
      return <TagsField field={field} value={value} onChange={set} />;
    case "select": {
      const choices = (options.data?.[field.optionsKey!] as { value: string; label: string }[] | undefined) ?? [];
      return (
        <TextField select label={field.label} value={(value as string) ?? ""} onChange={(e) => set(e.target.value)} required={field.required} helperText={field.help} fullWidth>
          {choices.map((c) => (
            <MenuItem key={c.value} value={c.value}>
              {c.label}
            </MenuItem>
          ))}
        </TextField>
      );
    }
    default:
      return (
        <TextField
          label={field.label}
          type={field.type === "textarea" ? "text" : field.type}
          multiline={field.type === "textarea"}
          minRows={field.type === "textarea" ? 2 : undefined}
          value={(value as string | number | null) ?? ""}
          onChange={(e) => set(e.target.value === "" ? null : field.type === "number" ? Number(e.target.value) : e.target.value)}
          required={field.required}
          helperText={field.help}
          fullWidth
          slotProps={{
            inputLabel: field.type === "date" ? { shrink: true } : undefined,
            htmlInput: field.type === "number" ? { min: 0, step: "0.01" } : undefined,
          }}
        />
      );
  }
}
