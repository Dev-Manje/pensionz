import { useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import { LoadingState } from "../../../../components/LoadingState";
import { PageHeader } from "../../../../components/PageHeader";
import { FormGrid, FormSection } from "../../../../components/form/FormLayout";
import { useFeedback } from "../../../../components/feedback/FeedbackProvider";
import { useCategory, useProposeCategory } from "../../../../queries/categories";
import { useFund } from "../../../../queries/funds";
import { useInvestmentOptions } from "../../../../queries/investmentOptions";
import { useScheme } from "../../../../queries/schemes";
import { formatDate, todayIso } from "../../../../utils/date";
import {
  SALARY_BASIS_LABELS,
  type BenefitCategory,
  type CategoryStatus,
  type CategoryTerms,
  type CategoryTermsInput,
  type Fund,
  type RateType,
  type SalaryBasis,
  type Scheme,
} from "../../../../api/types";

function emptyTerms(db: boolean): CategoryTermsInput {
  return {
    effective_from: todayIso(),
    employee_rate_type: "percent",
    employee_rate: "",
    employer_rate_type: "percent",
    employer_rate: db ? null : "",
    salary_basis: "basic",
    normal_retirement_age: null,
    min_entry_age: 18,
    max_entry_age: null,
    waiting_period_months: 0,
    vesting_scale: db ? [] : [{ years: 0, vested_pct: "100" }],
    default_investment_option_id: null,
    member_choice_allowed: false,
    avc_allowed: !db,
    group_life_multiple: null,
    accrual_denominator: db ? 60 : null,
    final_salary_months: db ? 36 : null,
  };
}

// Start new terms from the latest ones, so a change only touches what differs.
function fromTerms(t: CategoryTerms): CategoryTermsInput {
  const { id: _id, design: _design, default_investment_option: _label, ...rest } = t;
  return {
    ...rest,
    effective_from: todayIso() > t.effective_from ? todayIso() : t.effective_from,
    employee_rate: String(Number(t.employee_rate)),
    employer_rate: t.employer_rate === null ? null : String(Number(t.employer_rate)),
    group_life_multiple: t.group_life_multiple === null ? null : String(Number(t.group_life_multiple)),
    vesting_scale: t.vesting_scale.map((s) => ({ years: s.years, vested_pct: String(Number(s.vested_pct)) })),
  };
}

const num = (v: string) => (v === "" ? null : Number(v));

function RateField({ label, type, rate, onType, onRate, required = true }: { label: string; type: RateType; rate: string; onType: (t: RateType) => void; onRate: (r: string) => void; required?: boolean }) {
  return (
    <Stack direction="row" spacing={1}>
      <TextField
        label={label}
        type="number"
        value={rate}
        onChange={(e) => onRate(e.target.value)}
        required={required}
        fullWidth
        slotProps={{
          htmlInput: { min: 0, step: "0.01", max: type === "percent" ? 100 : undefined },
          input: {
            startAdornment: type === "fixed" ? <InputAdornment position="start">MWK</InputAdornment> : undefined,
            endAdornment: type === "percent" ? <InputAdornment position="end">%</InputAdornment> : undefined,
          },
        }}
      />
      <TextField select label="As" value={type} onChange={(e) => onType(e.target.value as RateType)} sx={{ minWidth: 130 }}>
        <MenuItem value="percent">% of salary</MenuItem>
        <MenuItem value="fixed">MWK a month</MenuItem>
      </TextField>
    </Stack>
  );
}

function TermsFields({ fund, terms, set, minDate }: { fund: Fund; terms: CategoryTermsInput; set: (patch: Partial<CategoryTermsInput>) => void; minDate?: string }) {
  const db = fund.fund_type === "defined_benefit";
  const options = useInvestmentOptions(fund.id);
  const activeOptions = (options.data ?? []).filter((o) => o.status === "active");
  const setStep = (i: number, patch: Partial<{ years: number; vested_pct: string }>) =>
    set({ vesting_scale: terms.vesting_scale.map((s, j) => (j === i ? { ...s, ...patch } : s)) });

  return (
    <>
      <FormSection title="Takes effect" description="Months before this date keep the terms that applied then.">
        <FormGrid>
          <TextField
            label="Effective from"
            type="date"
            value={terms.effective_from}
            onChange={(e) => set({ effective_from: e.target.value })}
            required
            slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: minDate } }}
            helperText={minDate ? `Must be after ${formatDate(minDate)}, the start of the latest terms.` : undefined}
          />
        </FormGrid>
      </FormSection>

      <FormSection title="Contributions" description="Rates are checked against the statutory minimums in force on the effective date.">
        <FormGrid>
          <RateField label="Employee rate" type={terms.employee_rate_type} rate={terms.employee_rate} onType={(t) => set({ employee_rate_type: t })} onRate={(r) => set({ employee_rate: r })} />
          {db ? (
            <TextField label="Employer rate" value="Balance of cost (set by the actuary)" disabled fullWidth />
          ) : (
            <RateField
              label="Employer rate"
              type={terms.employer_rate_type}
              rate={terms.employer_rate ?? ""}
              onType={(t) => set({ employer_rate_type: t })}
              onRate={(r) => set({ employer_rate: r })}
            />
          )}
          <TextField select label="Pensionable salary" value={terms.salary_basis} onChange={(e) => set({ salary_basis: e.target.value as SalaryBasis })} fullWidth>
            {(Object.keys(SALARY_BASIS_LABELS) as SalaryBasis[]).map((b) => (
              <MenuItem key={b} value={b}>
                {SALARY_BASIS_LABELS[b]}
              </MenuItem>
            ))}
          </TextField>
        </FormGrid>
      </FormSection>

      <FormSection title="Retirement and eligibility">
        <FormGrid>
          <TextField
            label="Normal retirement age"
            type="number"
            value={terms.normal_retirement_age ?? ""}
            onChange={(e) => set({ normal_retirement_age: num(e.target.value) })}
            required
            fullWidth
            slotProps={{ htmlInput: { min: 40, max: 80 } }}
            helperText="Must be within the statutory retirement age band."
          />
          <TextField label="Youngest entry age" type="number" value={terms.min_entry_age ?? ""} onChange={(e) => set({ min_entry_age: num(e.target.value) })} fullWidth />
          <TextField label="Oldest entry age" type="number" value={terms.max_entry_age ?? ""} onChange={(e) => set({ max_entry_age: num(e.target.value) })} fullWidth helperText="Leave blank for no limit." />
          <TextField
            label="Waiting period"
            type="number"
            value={terms.waiting_period_months}
            onChange={(e) => set({ waiting_period_months: Number(e.target.value || 0) })}
            fullWidth
            slotProps={{ htmlInput: { min: 0, max: 60 }, input: { endAdornment: <InputAdornment position="end">months</InputAdornment> } }}
            helperText="Months of employment before joining."
          />
        </FormGrid>
      </FormSection>

      {db ? (
        <FormSection title="Defined benefit formula" description="Pension = years of service × final salary ÷ accrual.">
          <FormGrid>
            <TextField
              label="Accrual"
              type="number"
              value={terms.accrual_denominator ?? ""}
              onChange={(e) => set({ accrual_denominator: num(e.target.value) })}
              required
              fullWidth
              slotProps={{ input: { startAdornment: <InputAdornment position="start">1 /</InputAdornment> } }}
              helperText="e.g. 60 for 1/60th of final salary per year of service."
            />
            <TextField
              label="Final salary averaged over"
              type="number"
              value={terms.final_salary_months ?? ""}
              onChange={(e) => set({ final_salary_months: num(e.target.value) })}
              required
              fullWidth
              slotProps={{ input: { endAdornment: <InputAdornment position="end">months</InputAdornment> } }}
            />
          </FormGrid>
        </FormSection>
      ) : (
        <>
          <FormSection title="Investment">
            <FormGrid>
              <TextField
                select
                label="Default investment option"
                value={terms.default_investment_option_id ?? ""}
                onChange={(e) => set({ default_investment_option_id: e.target.value || null })}
                required
                fullWidth
                helperText={activeOptions.length === 0 && !options.isLoading ? "Add an investment option to the fund first." : "Where new members' money goes."}
              >
                {activeOptions.map((o) => (
                  <MenuItem key={o.id} value={o.id}>
                    {o.code} — {o.name}
                  </MenuItem>
                ))}
              </TextField>
              <FormControlLabel control={<Switch checked={terms.member_choice_allowed} onChange={(e) => set({ member_choice_allowed: e.target.checked })} />} label="Members may choose their option" />
              <FormControlLabel control={<Switch checked={terms.avc_allowed} onChange={(e) => set({ avc_allowed: e.target.checked })} />} label="Voluntary contributions (AVC) allowed" />
            </FormGrid>
          </FormSection>

          <FormSection
            title="Vesting of employer money"
            description="The share of employer contributions a member keeps on leaving, by completed years of service. Unvested money goes to the reserve."
            action={
              <Button startIcon={<AddIcon />} onClick={() => set({ vesting_scale: [...terms.vesting_scale, { years: (terms.vesting_scale.at(-1)?.years ?? -1) + 1, vested_pct: "100" }] })}>
                Add step
              </Button>
            }
          >
            <Stack spacing={1.5}>
              {terms.vesting_scale.length === 0 && <Typography color="text.secondary">No scale — employer money is fully vested from joining.</Typography>}
              {terms.vesting_scale.map((s, i) => (
                <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center", maxWidth: 520 }}>
                  <TextField
                    label="After"
                    type="number"
                    size="small"
                    value={s.years}
                    onChange={(e) => setStep(i, { years: Number(e.target.value || 0) })}
                    slotProps={{ htmlInput: { min: 0, max: 60 }, input: { endAdornment: <InputAdornment position="end">years</InputAdornment> } }}
                  />
                  <TextField
                    label="Vested"
                    type="number"
                    size="small"
                    value={s.vested_pct}
                    onChange={(e) => setStep(i, { vested_pct: e.target.value })}
                    slotProps={{ htmlInput: { min: 0, max: 100, step: "0.01" }, input: { endAdornment: <InputAdornment position="end">%</InputAdornment> } }}
                  />
                  <IconButton aria-label={`Remove step ${i + 1}`} onClick={() => set({ vesting_scale: terms.vesting_scale.filter((_, j) => j !== i) })}>
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </Stack>
              ))}
            </Stack>
          </FormSection>
        </>
      )}

      <FormSection title="Insured benefits">
        <FormGrid>
          <TextField
            label="Group life cover"
            type="number"
            value={terms.group_life_multiple ?? ""}
            onChange={(e) => set({ group_life_multiple: e.target.value || null })}
            fullWidth
            slotProps={{ htmlInput: { min: 0, max: 20, step: "0.5" }, input: { endAdornment: <InputAdornment position="end">× annual salary</InputAdornment> } }}
            helperText="Leave blank if this category has no group life cover."
          />
        </FormGrid>
      </FormSection>
    </>
  );
}

// Add a category, or change one (rename/close and/or new terms from a later date).
export function CategoryFormPage() {
  const { fundId, schemeId, categoryId } = useParams();
  const fund = useFund(fundId);
  const scheme = useScheme(schemeId);
  const category = useCategory(categoryId);
  if (fund.isLoading || scheme.isLoading || (categoryId && category.isLoading)) return <LoadingState />;
  const error = fund.error ?? scheme.error ?? category.error;
  if (error || !fund.data || !scheme.data || (categoryId && !category.data)) return <Alert severity="error">{error?.message ?? "Not found"}</Alert>;
  return <CategoryForm key={categoryId ?? "new"} fund={fund.data} scheme={scheme.data} category={category.data ?? null} />;
}

function CategoryForm({ fund, scheme, category }: { fund: Fund; scheme: Scheme; category: BenefitCategory | null }) {
  const navigate = useNavigate();
  const feedback = useFeedback();
  const propose = useProposeCategory();
  const db = fund.fund_type === "defined_benefit";
  const latest = category?.history[0] ?? null;
  const [code, setCode] = useState("");
  const [name, setName] = useState(category?.name ?? "");
  const [status, setStatus] = useState<CategoryStatus>(category?.status ?? "active");
  const [changeTerms, setChangeTerms] = useState(!category);
  const [terms, setTerms] = useState<CategoryTermsInput>(() => (latest ? fromTerms(latest) : emptyTerms(db)));
  const [error, setError] = useState<string | null>(null);
  const base = `/funds/${fund.id}/employers/${scheme.id}`;
  const backTo = category ? `${base}/categories/${category.id}` : `${base}?tab=categories`;
  const set = (patch: Partial<CategoryTermsInput>) => setTerms((t) => ({ ...t, ...patch }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (category) {
        await propose.mutateAsync({ categoryId: category.id, name, status, terms: changeTerms ? terms : null });
      } else {
        await propose.mutateAsync({ schemeId: scheme.id, code, name, terms });
      }
      feedback.success("Sent for approval — a scheme-setup checker must approve it before it takes effect.");
      navigate(backTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/funds" underline="hover" color="inherit">
          Funds
        </Link>
        <Link component={RouterLink} to={`/funds/${fund.id}?tab=employers`} underline="hover" color="inherit">
          {fund.code}
        </Link>
        <Link component={RouterLink} to={`${base}?tab=categories`} underline="hover" color="inherit">
          {scheme.code}
        </Link>
        {category && (
          <Link component={RouterLink} to={backTo} underline="hover" color="inherit">
            {category.code}
          </Link>
        )}
        <Typography color="text.primary">{category ? "Change" : "New category"}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={category ? `Change ${category.name}` : `Add a benefit category to ${scheme.name}`}
        description="A scheme-setup checker approves the category before it takes effect."
      />
      <Stack component="form" spacing={2} onSubmit={submit}>
        <FormSection title="Category">
          <FormGrid>
            {!category && (
              <TextField
                label="Code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                slotProps={{ htmlInput: { maxLength: 10, style: { textTransform: "uppercase" } } }}
                helperText="e.g. MGT, STF — unique for this employer."
              />
            )}
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} required slotProps={{ htmlInput: { minLength: 2 } }} helperText="e.g. Management, Staff" />
            {category && (
              <TextField
                select
                label="Status"
                value={status}
                onChange={(e) => setStatus(e.target.value as CategoryStatus)}
                helperText={status === "closed" ? "Existing members stay; nobody new joins." : "Open to new members."}
              >
                <MenuItem value="active">Active</MenuItem>
                <MenuItem value="closed">Closed</MenuItem>
              </TextField>
            )}
          </FormGrid>
          {category && (
            <FormControlLabel
              sx={{ mt: 1 }}
              control={<Checkbox checked={changeTerms} onChange={(e) => setChangeTerms(e.target.checked)} />}
              label="Also change the terms (rates, retirement age, vesting…) from a date"
            />
          )}
        </FormSection>

        {changeTerms && <TermsFields fund={fund} terms={terms} set={set} minDate={latest?.effective_from} />}

        {error && <Alert severity="error">{error}</Alert>}
        <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end", pb: 2 }}>
          <Button component={RouterLink} to={backTo}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={propose.isPending}>
            {propose.isPending ? "Sending…" : "Submit for approval"}
          </Button>
        </Stack>
      </Stack>
    </>
  );
}
