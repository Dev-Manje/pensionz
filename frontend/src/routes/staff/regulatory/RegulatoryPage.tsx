import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import { PageHeader } from "../../../components/PageHeader";
import { useUrlTab } from "../../../hooks/useUrlState";
import { ParametersTab } from "./ParametersTab";
import { TaxTablesTab } from "./TaxTablesTab";

const TABS = ["parameters", "tax-tables"] as const;
type RegTab = (typeof TABS)[number];

// System-wide regulatory figures and tax tables (FR-CFG-009). Every change is a
// new version from an effective date, approved by a scheme-setup checker.
export function RegulatoryPage() {
  const [tab, setTab] = useUrlTab(TABS);
  return (
    <>
      <PageHeader
        title="Regulatory"
        description="Statutory figures and tax tables that apply to every fund. A change takes effect from its date once a scheme-setup checker approves it; earlier dates keep the values that applied then."
      />
      <Tabs value={tab} onChange={(_, v: RegTab) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="parameters" label="Parameters" />
        <Tab value="tax-tables" label="Tax tables" />
      </Tabs>
      {tab === "parameters" && <ParametersTab />}
      {tab === "tax-tables" && <TaxTablesTab />}
    </>
  );
}
