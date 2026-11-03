import { Route, Routes } from "react-router-dom";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import { PageHeader } from "../../../components/PageHeader";
import { useUrlTab } from "../../../hooks/useUrlState";
import { ApplicationReviewPage } from "./ApplicationReviewPage";
import { ApplicationsTab } from "./ApplicationsTab";
import { OfficersTab } from "./OfficersTab";

const TABS = ["officers", "applications"] as const;
type OnboardingTab = (typeof TABS)[number];

// Onboarding (decided 2026-11-03): staff add principal officers for funds; the
// officers apply in the portal for their employers to join; scheme setup reviews.
function OnboardingHome() {
  const [tab, setTab] = useUrlTab(TABS);
  return (
    <>
      <PageHeader
        title="Onboarding"
        description="Principal officers who use the portal, and the employers they apply to bring into a fund."
      />
      <Stack spacing={2}>
        <Tabs value={tab} onChange={(_, v: OnboardingTab) => setTab(v)} variant="scrollable" scrollButtons={false}>
          <Tab value="officers" label="Principal officers" />
          <Tab value="applications" label="Employer applications" />
        </Tabs>
        <div>{tab === "officers" ? <OfficersTab /> : <ApplicationsTab />}</div>
      </Stack>
    </>
  );
}

export function OnboardingPage() {
  return (
    <Routes>
      <Route index element={<OnboardingHome />} />
      <Route path="applications/:applicationId" element={<ApplicationReviewPage />} />
    </Routes>
  );
}
