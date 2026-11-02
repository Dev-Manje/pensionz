import { Route, Routes } from "react-router-dom";
import { PoHome } from "./PoHome";
import { PoKycPage } from "./PoKycPage";
import { PoSchemePage } from "./PoSchemePage";

// Principal officer portal (/po): the dashboard, one page per employer with its
// sections as tabs, and the employer's KYC applications. Officers have no
// sidebar — they move between employers from the dashboard or the employer switcher.
export function PoPortal() {
  return (
    <Routes>
      <Route index element={<PoHome />} />
      <Route path="schemes/:schemeId" element={<PoSchemePage />} />
      <Route path="kyc/:applicationId" element={<PoKycPage />} />
    </Routes>
  );
}
