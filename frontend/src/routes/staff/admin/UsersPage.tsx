import { useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import FormLabel from "@mui/material/FormLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { RowActions } from "../../../components/RowActions";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useProposeUser, useProposeUserUpdate, useSendPasswordLink, useUsers } from "../../../queries/users";
import { formatDateTime } from "../../../utils/date";
import { PORTAL_ROLES, ROLE_LABELS, STAFF_ROLES, type User, type UserRole, type UserStatus } from "../../../api/types";

function RolePicker({ value, onChange }: { value: UserRole[]; onChange: (roles: UserRole[]) => void }) {
  const toggle = (role: UserRole) => onChange(value.includes(role) ? value.filter((r) => r !== role) : [...value, role]);
  const group = (title: string, roles: UserRole[]) => (
    <Stack spacing={0.5}>
      <FormLabel component="legend" sx={{ fontSize: "0.8125rem", fontWeight: 600 }}>
        {title}
      </FormLabel>
      <FormGroup sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
        {roles.map((r) => (
          <FormControlLabel key={r} control={<Checkbox size="small" checked={value.includes(r)} onChange={() => toggle(r)} />} label={ROLE_LABELS[r]} />
        ))}
      </FormGroup>
    </Stack>
  );
  return (
    <Stack spacing={1.5} component="fieldset" sx={{ border: 0, p: 0, m: 0 }}>
      {group("Staff roles", STAFF_ROLES)}
      {group("Portal roles", PORTAL_ROLES)}
    </Stack>
  );
}

function UserDialog({ user, onClose }: { user: User | null; onClose: () => void }) {
  const propose = useProposeUser();
  const update = useProposeUserUpdate();
  const feedback = useFeedback();
  const [email, setEmail] = useState(user?.email ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [roles, setRoles] = useState<UserRole[]>(user?.roles ?? []);
  const [status, setStatus] = useState<UserStatus>(user?.status ?? "active");
  const [error, setError] = useState<string | null>(null);
  const busy = propose.isPending || update.isPending;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (roles.length === 0) {
      setError("Choose at least one role.");
      return;
    }
    try {
      if (user) {
        await update.mutateAsync({ id: user.id, input: { full_name: fullName, phone: phone || null, roles, status } });
      } else {
        await propose.mutateAsync({ email, full_name: fullName, phone: phone || null, roles });
      }
      feedback.success("Sent for approval — another administrator must approve it before it takes effect.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={submit}>
        <DialogTitle>{user ? `Change ${user.full_name || user.email}` : "Add a user"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="info">
              {user ? "Changes" : "New users"} need approval from a second administrator. Once approved, a new user gets an
              email invitation to set their own password.
            </Alert>
            {!user && (
              <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required fullWidth autoComplete="off" />
            )}
            <TextField label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required fullWidth slotProps={{ htmlInput: { minLength: 2 } }} />
            <TextField label="Phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} fullWidth helperText="Optional, e.g. 0999 123 456" />
            {user && (
              <TextField select label="Status" value={status} onChange={(e) => setStatus(e.target.value as UserStatus)} fullWidth helperText="Suspending signs the user out at once.">
                <MenuItem value="active">Active</MenuItem>
                <MenuItem value="suspended">Suspended</MenuItem>
                <MenuItem value="deactivated">Deactivated</MenuItem>
              </TextField>
            )}
            <RolePicker value={roles} onChange={setRoles} />
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={busy}>
            {busy ? "Sending…" : "Send for approval"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

function userStatus(u: User) {
  if (u.locked) return "locked";
  if (u.status === "active" && u.awaiting_setup) return "awaiting_setup";
  return u.status;
}

// Staff and portal logins (FR-SEC-001). Admins propose; another admin approves.
export function UsersPage() {
  const { user: me } = useAuth();
  const isAdmin = me?.roles.includes("admin") ?? false;
  const [q, setQ] = useState("");
  const users = useUsers(q.trim());
  const sendLink = useSendPasswordLink();
  const feedback = useFeedback();
  const [editing, setEditing] = useState<User | "new" | null>(null);

  async function link(u: User) {
    try {
      await sendLink.mutateAsync(u.id);
      feedback.success(`${u.awaiting_setup ? "Invitation" : "Password reset link"} sent to ${u.email}.`);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't send the link.");
    }
  }

  const rows = users.data ?? [];
  return (
    <>
      <PageHeader
        title="Users"
        description="Staff, principal officers and members who can sign in. Every change is approved by a second administrator."
        action={isAdmin && <Button variant="contained" onClick={() => setEditing("new")}>Add user</Button>}
      />
      <TextField
        label="Search by name or email"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        size="small"
        sx={{ mb: 2, width: { xs: "100%", sm: 320 } }}
      />
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Roles</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Last sign-in</TableCell>
              {isAdmin && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={isAdmin ? 6 : 5}
              loading={users.isLoading}
              error={users.error?.message ?? null}
              onRetry={() => users.refetch()}
              empty={q ? "No users match that search." : "No users yet. Add the first one with “Add user”."}
              count={rows.length}
            />
            {rows.map((u) => (
              <TableRow key={u.id} hover>
                <TableCell sx={{ fontWeight: 500 }}>{u.full_name || "—"}</TableCell>
                <TableCell>{u.email}</TableCell>
                <TableCell>
                  <Typography variant="body2">{u.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</Typography>
                </TableCell>
                <TableCell>
                  <StatusChip status={userStatus(u)} />
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}</TableCell>
                {isAdmin && (
                  <TableCell align="right">
                    <RowActions
                      actions={[
                        { label: "Change", onClick: () => setEditing(u) },
                        ...(u.status === "active"
                          ? [{ label: u.awaiting_setup ? "Resend invitation" : "Send password reset link", onClick: () => link(u) }]
                          : []),
                      ]}
                    />
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      {editing && <UserDialog user={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}
