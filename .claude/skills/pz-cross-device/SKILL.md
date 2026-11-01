---
name: pz-cross-device
description: Use when building or reviewing any Pensionz screen for how it behaves across devices, screen sizes, browsers, network conditions and accessibility needs — phones, tablets, desktops, touch vs mouse, slow mobile data, printing (statements, vouchers), screen readers, older members. Especially for member and individual portals.
---

# Cross-device, cross-platform UX

## Who uses what (assumptions — confirm with the business)

| Audience | Likely device | Implications |
|---|---|---|
| Members, pensioners, personal-pension holders | Android phones, often low-end, mobile data; many older users | Phone-first, light pages, large text option, very plain language |
| Principal officers (employer HR/payroll who remit) | Office Windows laptop, Excel | Upload/download Excel templates; tables; tablet OK |
| Administrator staff | Windows desktop, Chrome/Edge, large tables, heavy keyboard use | Dense views at 1366–1920px; keyboard shortcuts |
| Trustees | Laptop/tablet in meetings | Readable reports, PDF downloads |

Support: last 2 versions of Chrome, Edge, Firefox, Safari (macOS + iOS 16+), Samsung Internet.

## Breakpoints & layout

- MUI defaults; test at **360, 390, 768, 1366, 1920** px.
- Sidebar permanent on `md+`, hamburger on `xs/sm`; dialogs `fullScreen` on `xs`.
- Phone tables → stacked cards; never sideways scroll for primary info.
- Correct input types (`inputMode="decimal"`, `type="tel"`, `autoComplete`); date pickers
  usable on touch; national ID fields uppercase.

## Network & performance

- Portal budget: first load < 300KB JS gzipped, usable within 3s on Fast 3G.
- Skeletons for lists; keep data visible while refreshing; retry on failure; no double-submits.
- Large uploads (KYC images from phone cameras): compress client-side, show progress, resume
  on failure where possible.

## Accessibility (WCAG 2.1 AA)

Contrast ≥ 4.5:1; visible labels; errors in text; logical headings; `aria-label` on icon
buttons; focus visible; zoom to 200%; respect reduced motion.

## Localisation & formats

`MWK 1,250,000.00`, `2 Oct 2026`, 24h time, `+265 …`; shared formatters only. Copy short;
room for Chichewa later *(confirm need)*.

## Print & documents

Statements, payment vouchers, benefit quotes, tax certificates are server PDFs. Screens users
print get `@media print` rules.

## Verify

`pz-verify` CDP flow at 360×740 (mobile, dpr 3), 768×1024, 1366×768, 1920×1080, plus slow-3G
emulation on portal pages. Look at every screenshot.
