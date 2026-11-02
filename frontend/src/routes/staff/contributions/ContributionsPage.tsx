import { useEffect } from "react";
import { Route, Routes } from "react-router-dom";
import Alert from "@mui/material/Alert";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import { LoadingState } from "../../../components/LoadingState";
import { PageHeader } from "../../../components/PageHeader";
import { useUrlParam, useUrlTab } from "../../../hooks/useUrlState";
import { useFunds } from "../../../queries/funds";
import { ReceiptDetailPage } from "./ReceiptDetailPage";
import { ReceiptsTab } from "./ReceiptsTab";
import { ScheduleDetailPage } from "./ScheduleDetailPage";
import { SchedulesTab } from "./SchedulesTab";

const TABS = ["receipts", "schedules"] as const;
type ContributionsTab = (typeof TABS)[number];

// Contributions back office (FR-CON): money in, schedules, allocation and arrears per fund.
function ContributionsHome() {
  const funds = useFunds();
  const [fundId, setFundId] = useUrlParam("fund");
  const [tab, setTab] = useUrlTab(TABS);
  const list = funds.data ?? [];

  // Default to the first fund the user administers.
  useEffect(() => {
    if (!fundId && list.length) setFundId(list[0].id);
  }, [fundId, list.length]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <PageHeader title="Contributions" description="Money received from employers, contribution schedules and allocation to members." />
      {funds.isLoading ? (
        <LoadingState />
      ) : !list.length ? (
        <Alert severity="info">You don't administer any funds yet. Ask an administrator to give you access.</Alert>
      ) : (
        <Stack spacing={2}>
          <TextField select size="small" label="Fund" value={fundId ?? ""} onChange={(e) => setFundId(e.target.value)} sx={{ maxWidth: 420 }}>
            {list.map((f) => (
              <MenuItem key={f.id} value={f.id}>{f.code} — {f.name}</MenuItem>
            ))}
          </TextField>
          <Tabs value={tab} onChange={(_, v: ContributionsTab) => setTab(v)} variant="scrollable" scrollButtons={false}>
            <Tab value="receipts" label="Money received" />
            <Tab value="schedules" label="Schedules" />
          </Tabs>
          {fundId && tab === "receipts" && <ReceiptsTab fundId={fundId} />}
          {fundId && tab === "schedules" && <SchedulesTab fundId={fundId} />}
        </Stack>
      )}
    </>
  );
}

export function ContributionsPage() {
  return (
    <Routes>
      <Route index element={<ContributionsHome />} />
      <Route path="receipts/:receiptId" element={<ReceiptDetailPage />} />
      <Route path="schedules/:scheduleId" element={<ScheduleDetailPage />} />
    </Routes>
  );
}
