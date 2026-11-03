import { useState, type ReactNode } from "react";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { openArrearsStatement, openContributionStatement, openInvoice } from "../../api/po";
import { formatPeriod } from "../../utils/date";
import { recentMonths } from "./poLabels";

function Card({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>{title}</Typography>
      <Typography color="text.secondary" sx={{ mb: 1.5, maxWidth: 640 }}>{text}</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
        {children}
      </Stack>
    </Paper>
  );
}

function MonthPicker({ label, value, onChange, months }: { label: string; value: string; onChange: (v: string) => void; months: string[] }) {
  return (
    <TextField select size="small" label={label} value={value} onChange={(e) => onChange(e.target.value)} sx={{ minWidth: 170 }}>
      {months.map((m) => (
        <MenuItem key={m} value={m}>{formatPeriod(m)}</MenuItem>
      ))}
    </TextField>
  );
}

// Employer documents (PDF): what to pay for a month, what was credited over a period, and arrears.
export function PoStatements({ schemeId }: { schemeId: string }) {
  const feedback = useFeedback();
  const months = recentMonths(new Date(), 24);
  const [invoiceMonth, setInvoiceMonth] = useState(months[1]);
  const [from, setFrom] = useState(months[Math.min(12, months.length - 1)]);
  const [to, setTo] = useState(months[1]);
  const open = (p: Promise<void>) => p.catch((e) => feedback.error(e instanceof Error ? e.message : "Couldn't open the document."));

  return (
    <Stack spacing={2}>
      <Card title="Contribution invoice" text="What to pay for a month: each member's contributions from the salary on record, any fees you pay, the due date and the fund's bank account.">
        <MonthPicker label="Contributions for" value={invoiceMonth} onChange={setInvoiceMonth} months={months} />
        <Button variant="contained" onClick={() => open(openInvoice(schemeId, invoiceMonth))}>Download invoice</Button>
      </Card>
      <Card title="Statement of contributions" text="Month by month, what your schedules said, what was credited to members and what was paid — with each member's totals.">
        <MonthPicker label="From" value={from} onChange={setFrom} months={months} />
        <MonthPicker label="To" value={to} onChange={setTo} months={months} />
        <Button variant="contained" disabled={from > to} onClick={() => open(openContributionStatement(schemeId, from, to))}>Download statement</Button>
      </Card>
      <Card title="Arrears statement" text="Months not fully paid, how long they are overdue and any late-payment interest, as at today.">
        <Button variant="contained" onClick={() => open(openArrearsStatement(schemeId))}>Download arrears statement</Button>
      </Card>
    </Stack>
  );
}
