import { useMemo, useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { LoadingState } from "../../../components/LoadingState";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useUrlParam } from "../../../hooks/useUrlState";
import { useListRows, useListSpecs, useProposeListRow } from "../../../queries/setup";
import type { ListField, ListRow, SystemListSpec } from "../../../api/types";

function display(field: ListField, row: ListRow): string {
  const value = row[field.name];
  if (value === null || value === undefined || value === "") return "—";
  if (field.type === "boolean") return value ? "Yes" : "No";
  if (field.type === "select") return field.options.find((o) => o.value === value)?.label ?? String(value);
  if (field.type === "ref") return String(row[`${field.name}_label`] ?? "—");
  return String(value);
}

// A reference field picks from another list (e.g. a branch's bank).
function RefField({ field, value, onChange, disabled }: { field: ListField; value: string | null; onChange: (v: string | null) => void; disabled: boolean }) {
  const rows = useListRows(field.ref);
  const options = (rows.data ?? []).filter((r) => r.active !== false || r.id === value);
  const selected = options.find((r) => r.id === value) ?? null;
  return (
    <Autocomplete
      options={options}
      value={selected}
      loading={rows.isLoading}
      disabled={disabled}
      onChange={(_, row) => onChange(row?.id ?? null)}
      getOptionLabel={(r) => String(r.name ?? r.code ?? "")}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      renderInput={(params) => <TextField {...params} label={field.label} required={field.required} helperText={field.help ?? undefined} />}
    />
  );
}

function RowDialog({ spec, row, parent, onClose }: { spec: SystemListSpec; row: ListRow | null; parent: string | null; onClose: () => void }) {
  const propose = useProposeListRow(spec.name);
  const feedback = useFeedback();
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(
      spec.fields.map((f) => [f.name, row ? row[f.name] : f.name === spec.parent_field ? parent : (f.default ?? (f.type === "boolean" ? false : null))]),
    ),
  );
  const [error, setError] = useState<string | null>(null);
  const set = (name: string, value: unknown) => setValues((v) => ({ ...v, [name]: value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await propose.mutateAsync({ id: row?.id, body: values });
      feedback.success("Sent for approval — a scheme-setup checker must approve it.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={submit}>
        <DialogTitle>{row ? `Change ${spec.label.toLowerCase()}` : `Add a ${spec.label.toLowerCase()}`}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {spec.fields.map((f) => {
              const locked = !!row && f.locked_on_edit;
              const value = values[f.name];
              const helper = locked ? "Can't change once set." : (f.help ?? undefined);
              if (f.type === "boolean") {
                return (
                  <Box key={f.name}>
                    <FormControlLabel control={<Switch checked={!!value} onChange={(e) => set(f.name, e.target.checked)} />} label={f.label} />
                    {f.help && (
                      <Typography variant="caption" color="text.secondary" component="p">
                        {f.help}
                      </Typography>
                    )}
                  </Box>
                );
              }
              if (f.type === "ref") return <RefField key={f.name} field={f} value={(value as string) ?? null} onChange={(v) => set(f.name, v)} disabled={locked} />;
              if (f.type === "select") {
                return (
                  <TextField key={f.name} select label={f.label} value={(value as string) ?? ""} onChange={(e) => set(f.name, e.target.value)} required={f.required} disabled={locked} helperText={helper}>
                    {f.options.map((o) => (
                      <MenuItem key={o.value} value={o.value}>
                        {o.label}
                      </MenuItem>
                    ))}
                  </TextField>
                );
              }
              return (
                <TextField
                  key={f.name}
                  label={f.label}
                  type={f.type === "number" ? "number" : "text"}
                  value={value ?? ""}
                  onChange={(e) => set(f.name, e.target.value === "" ? null : e.target.value)}
                  required={f.required}
                  disabled={locked}
                  helperText={helper}
                  slotProps={{
                    htmlInput: {
                      maxLength: f.max_length ?? undefined,
                      min: f.minimum ?? undefined,
                      max: f.maximum ?? undefined,
                      style: f.upper ? { textTransform: "uppercase" } : undefined,
                    },
                  }}
                />
              );
            })}
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={propose.isPending}>
            {propose.isPending ? "Sending…" : "Send for approval"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

function ParentPicker({ spec, field, value, onChange }: { spec: SystemListSpec; field: ListField; value: string | null; onChange: (v: string | null) => void }) {
  const rows = useListRows(field.ref);
  return (
    <TextField select size="small" label={`Show ${spec.plural.toLowerCase()} of`} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} sx={{ minWidth: 260 }}>
      <MenuItem value="">
        <em>All {field.label.toLowerCase()}s</em>
      </MenuItem>
      {(rows.data ?? []).map((r) => (
        <MenuItem key={r.id} value={r.id}>
          {String(r.name)}
        </MenuItem>
      ))}
    </TextField>
  );
}

function ListPanel({ spec, canChange }: { spec: SystemListSpec; canChange: boolean }) {
  const [parent, setParent] = useUrlParam("parent");
  const parentField = spec.parent_field ? spec.fields.find((f) => f.name === spec.parent_field) ?? null : null;
  const rows = useListRows(spec.name, parentField ? parent : null);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<ListRow | "new" | null>(null);
  const columns = spec.fields.filter((f) => f.column && f.name !== "active");
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const all = rows.data ?? [];
    return needle ? all.filter((r) => columns.some((c) => display(c, r).toLowerCase().includes(needle))) : all;
  }, [rows.data, q, columns]);

  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h6" component="h2">
            {spec.plural}
          </Typography>
          <Typography color="text.secondary" sx={{ maxWidth: 640 }}>
            {spec.description}
          </Typography>
        </Box>
        {canChange && (
          <Button variant="contained" onClick={() => setEditing("new")}>
            Add {spec.label.toLowerCase()}
          </Button>
        )}
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        {parentField && <ParentPicker spec={spec} field={parentField} value={parent} onChange={setParent} />}
        <TextField size="small" label="Search" value={q} onChange={(e) => setQ(e.target.value)} sx={{ width: { xs: "100%", sm: 260 } }} />
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              {columns.map((c) => (
                <TableCell key={c.name}>{c.label}</TableCell>
              ))}
              <TableCell>Status</TableCell>
              {canChange && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={columns.length + (canChange ? 2 : 1)}
              loading={rows.isLoading}
              error={rows.error?.message ?? null}
              onRetry={() => rows.refetch()}
              empty={q ? "Nothing matches that search." : `No ${spec.plural.toLowerCase()} yet.`}
              count={shown.length}
            />
            {shown.map((r) => (
              <TableRow key={r.id} hover>
                {columns.map((c, i) => (
                  <TableCell key={c.name} sx={i === 0 ? { fontWeight: 600 } : undefined}>
                    {display(c, r)}
                  </TableCell>
                ))}
                <TableCell>
                  <StatusChip status={r.active === false ? "retired" : "active"} />
                  {r.pending_approval_id && (
                    <RouterLink to={`/approvals/${r.pending_approval_id}`} aria-label="View the waiting change">
                      <StatusChip status="change_pending" clickable sx={{ ml: 0.5 }} />
                    </RouterLink>
                  )}
                </TableCell>
                {canChange && (
                  <TableCell align="right">
                    {!r.pending_approval_id && (
                      <Button size="small" onClick={() => setEditing(r)}>
                        Change
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      {editing && <RowDialog spec={spec} row={editing === "new" ? null : editing} parent={parent} onClose={() => setEditing(null)} />}
    </Stack>
  );
}

// Setup → system-wide lists (ledger codes, banks, places, pick-lists). Every
// list is described by the backend; changes go to a scheme-setup checker.
export function SetupPage() {
  const { user } = useAuth();
  const canChange = user?.roles.includes("scheme_config_maker") ?? false;
  const specs = useListSpecs();
  const [listName, setListName] = useUrlParam("list");
  const [, setParent] = useUrlParam("parent");
  const narrow = useMediaQuery(useTheme().breakpoints.down("md"));

  if (specs.isLoading) return <LoadingState />;
  if (specs.error || !specs.data) return <Alert severity="error">{specs.error?.message ?? "Couldn't load the lists."}</Alert>;
  const all = specs.data;
  const current = all.find((s) => s.name === listName) ?? all[0];
  const groups = [...new Set(all.map((s) => s.group))];
  const choose = (name: string) => {
    setParent(null);
    setListName(name);
  };

  return (
    <>
      <PageHeader title="Setup" description="Lists used across every fund — ledger codes, banks, places and pick-lists. Changes are approved by a scheme-setup checker; entries are retired, never deleted." />
      <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ alignItems: "flex-start" }}>
        {narrow ? (
          <TextField select label="List" value={current.name} onChange={(e) => choose(e.target.value)} fullWidth>
            {all.map((s) => (
              <MenuItem key={s.name} value={s.name}>
                {s.group} · {s.plural}
              </MenuItem>
            ))}
          </TextField>
        ) : (
          <Paper sx={{ width: 240, flexShrink: 0 }}>
            <List dense component="nav" aria-label="Setup lists">
              {groups.map((g) => (
                <Box key={g}>
                  <ListSubheader sx={{ lineHeight: "32px", bgcolor: "transparent", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "text.secondary", mt: 1 }}>
                    {g}
                  </ListSubheader>
                  {all
                    .filter((s) => s.group === g)
                    .map((s) => (
                      <ListItemButton key={s.name} selected={s.name === current.name} onClick={() => choose(s.name)} aria-current={s.name === current.name ? "page" : undefined}>
                        <ListItemText primary={s.plural} />
                      </ListItemButton>
                    ))}
                </Box>
              ))}
            </List>
          </Paper>
        )}
        <Box sx={{ flex: 1, minWidth: 0, width: "100%" }}>
          <ListPanel key={current.name} spec={current} canChange={canChange} />
        </Box>
      </Stack>
    </>
  );
}
