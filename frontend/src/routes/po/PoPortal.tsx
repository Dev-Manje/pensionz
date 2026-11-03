import { Route, Routes } from "react-router-dom";
import { PoApplicationPage } from "./PoApplicationPage";
import { PoHome } from "./PoHome";
import { PoImportPage } from "./PoImportPage";
import { PoKycPage } from "./PoKycPage";
import { PoMemberPage } from "./PoMemberPage";
import { PoPaymentPage } from "./PoPaymentPage";
import { PoSchedulePage } from "./PoSchedulePage";
import { PoRequestPage } from "./PoRequests";
import { PoSchemePage } from "./PoSchemePage";

// Principal officer portal (/po): the dashboard, one page per employer with its
// sections as tabs, and the employer's KYC applications. Officers have no
// sidebar — they move between employers from the dashboard or the employer switcher.
export function PoPortal() {
  return (
    <Routes>
      <Route index element={<PoHome />} />
      <Route path="schemes/:schemeId" element={<PoSchemePage />} />
      <Route path="applications/:applicationId" element={<PoApplicationPage />} />
      <Route path="kyc/:applicationId" element={<PoKycPage />} />
      <Route path="schedules/:scheduleId" element={<PoSchedulePage />} />
      <Route path="remittances/:paymentId" element={<PoPaymentPage />} />
      <Route path="members/:memberId" element={<PoMemberPage />} />
      <Route path="member-imports/:importId" element={<PoImportPage />} />
      <Route path="requests/:requestId" element={<PoRequestPage />} />
    </Routes>
  );
}
