import { useEffect, useState } from "react";
import { Link as RouterLink, Route, Routes, useNavigate } from "react-router-dom";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useAuth } from "../../../auth/AuthContext";
import { useUrlParam } from "../../../hooks/useUrlState";
import { useFunds } from "../../../queries/funds";
import { useSchemes } from "../../../queries/schemes";
import { useMembers } from "../../../queries/members";
import { MEMBER_STATUS_LABELS, type MemberStatus } from "../../../api/types";
import { formatDate } from "../../../utils/date";
import { MemberDetailPage } from "./MemberDetailPage";
import { MemberFormPage } from "./MemberFormPage";
import { MemberImportPage } from "./MemberImportPage";

// Membership (FR-MEM): /members, /members/new, /members/import, /members/<id>, /members/<id>/edit.
export function MembersPage() {
  return (
    <Routes>
      <Route index element={<MemberList />} />
      <Route path="new" element={<MemberFormPage />} />
      <Route path="import" element={<MemberImportPage />} />
      <Route path=":memberId" element={<MemberDetailPage />} />
      <Route path=":memberId/edit" element={<MemberFormPage />} />
    </Routes>
  );
}

function SchemeFilter({ fundId, value, onChange }: { fundId: string; value: string | null; onChange: (v: string | null) => void }) {
  const schemes = useSchemes(fundId);
  return (
    <TextField select size="small" label="Employer" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} sx={{ minWidth: 200 }}>
      <MenuItem value="">All employers</MenuItem>
      {(schemes.data ?? []).map((s) => (
        <MenuItem key={s.id} value={s.id}>
          {s.code} — {s.name}
        </MenuItem>
      ))}
    </TextField>
  );
}

function MemberList() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canCreate = user?.roles.includes("member_admin") ?? false;
  const funds = useFunds();
  const [fundId, setFundId] = useUrlParam("fund");
  const [schemeId, setSchemeId] = useUrlParam("employer");
  const [status, setStatus] = useUrlParam("status");
  const [q, setQ] = useUrlParam("q");
  const [pageParam, setPageParam] = useUrlParam("page");
  const [search, setSearch] = useState(q ?? "");
  const [pageSize, setPageSize] = useState(25);
  const page = Math.max(0, Number(pageParam ?? 1) - 1);

  // Search as the user types, without a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      if ((q ?? "") !== search.trim()) {
        setQ(search.trim() || null);
        setPageParam(null);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [search]); // eslint-disable-line react-hooks/exhaustive-deps

  const members = useMembers({ fund_id: fundId, scheme_id: schemeId, status: status as MemberStatus | null, q: q ?? "", page: page + 1, page_size: pageSize });
  const rows = members.data?.items ?? [];
  const filtered = !!(fundId || schemeId || status || q);

  return (
    <>
      <PageHeader
        title="Members"
        description="Members of the funds you administer. New members, corrections and status changes are approved by a member checker."
        action={
          canCreate && (
            <Stack direction="row" spacing={1}>
              <Button variant="outlined" onClick={() => navigate(fundId ? `/members/import?fund=${fundId}` : "/members/import")}>
                Bulk upload
              </Button>
              <Button variant="contained" onClick={() => navigate(fundId ? `/members/new?fund=${fundId}` : "/members/new")}>
                Add member
              </Button>
            </Stack>
          )
        }
      />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} useFlexGap sx={{ mb: 2, flexWrap: "wrap" }}>
        <TextField size="small" label="Search" placeholder="Name, account code, employee or ID number" value={search} onChange={(e) => setSearch(e.target.value)} sx={{ minWidth: { sm: 320 } }} />
        <TextField select size="small" label="Fund" value={fundId ?? ""} onChange={(e) => { setFundId(e.target.value || null); setSchemeId(null); setPageParam(null); }} sx={{ minWidth: 180 }}>
          <MenuItem value="">All funds</MenuItem>
          {(funds.data ?? []).map((f) => (
            <MenuItem key={f.id} value={f.id}>
              {f.code} — {f.name}
            </MenuItem>
          ))}
        </TextField>
        {fundId && <SchemeFilter fundId={fundId} value={schemeId} onChange={(v) => { setSchemeId(v); setPageParam(null); }} />}
        <TextField select size="small" label="Status" value={status ?? ""} onChange={(e) => { setStatus(e.target.value || null); setPageParam(null); }} sx={{ minWidth: 160 }}>
          <MenuItem value="">Any status</MenuItem>
          {(Object.keys(MEMBER_STATUS_LABELS) as MemberStatus[]).map((s) => (
            <MenuItem key={s} value={s}>
              {MEMBER_STATUS_LABELS[s]}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Account code</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Fund / employer</TableCell>
              <TableCell>Employee no.</TableCell>
              <TableCell>ID number</TableCell>
              <TableCell>Born</TableCell>
              <TableCell>Joined</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={8}
              loading={members.isLoading}
              error={members.error?.message ?? null}
              onRetry={() => members.refetch()}
              empty={filtered ? "No members match these filters." : canCreate ? "No members yet. Add the first one with “Add member”." : "No members in your funds yet."}
              count={rows.length}
            />
            {rows.map((m) => (
              <TableRow key={m.id} hover>
                <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                  <Link component={RouterLink} to={`/members/${m.id}`} underline="hover">
                    {m.account_code}
                  </Link>
                </TableCell>
                <TableCell>{m.full_name}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {m.fund_code}
                  {m.employer_code ? ` / ${m.employer_code}` : ""}
                  {m.category_code ? ` · ${m.category_code}` : ""}
                </TableCell>
                <TableCell>{m.employee_no ?? "—"}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{m.id_number_masked ?? "—"}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(m.date_of_birth)}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(m.date_joined_fund)}</TableCell>
                <TableCell>
                  <StatusChip status={m.status} />
                  {m.pending_approval_id && <StatusChip status="change_pending" sx={{ ml: 0.5 }} />}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
        <TablePagination
          component="div"
          count={members.data?.total ?? 0}
          page={page}
          rowsPerPage={pageSize}
          rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, p) => setPageParam(p === 0 ? null : String(p + 1))}
          onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPageParam(null); }}
        />
      </TableContainer>
    </>
  );
}
