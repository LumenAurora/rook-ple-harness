# Key results — E119 companion-simulation validation (mirrors the Word memo CFDME-2025-041_E119_validation_memo_20251010.docx)

Deliverable of record: output/CFDME-2025-041_E119_validation_memo_20251010.docx (Word memo, 10/10/2025).

Straight answer: NOT validated. E = +13 min exceeds both the acceptance criterion and u_val; report as a documented finding.

Assembly/certification: the run's assembly (OAS-WUI-01_revC) matches the Ironwood-certified geometry
(IWFPE-CERT-25-0374 §1.2 = RBFMT-25-0918 §2: 50 mm leaves / 205 mm open-air cavity / 305 mm overall;
3.8 mm 9-gauge ties at 600 mm o.c., 25 mm embedment, siliceous aggregate, non-load-bearing),
parameter for parameter, per dimensioned section OAS-WA-305mm-DW. Caveat: checklist item 7 (revC↔case-log
cross-check) open; revD (parapet, 10/09/2025) is not the run's geometry and is outside certification scope.

Governing criterion (earlier of the two governs, ASTM E119): single-point, 181 °C rise (202.0 °C absolute,
21.0 °C initial ambient). Crossing times, to the nearest minute:
  - Single-point (181 °C rise): test 118 min (TC-6 over tie course) | run 131 min
  - Average (139 °C rise):      test 163 min                      | run 176 min
Section 7 stub prediction S = 131 min: stands as the run's read; its implicit "validated" claim does not.

D adopted: 118 min (as-tested, RBFMT-25-0918). Bianca's revised 129 min (TC-6 post-test calibration
correction): NOT adopted — no reissued lab report, no calibration certificate of record; recorded in
correspondence file only (Procedure §6).

Rollup (S, D, E, u_val, criterion):
  S = 131 min | D = 118 min | E = +13 min (over-predicts endurance) | u_val = ±9 min
  (RSS of u_num ±4 min, u_inp ±6 min, u_exp ±5 min = 8.77 min, to whole minutes)
  Acceptance: |E| ≤ 10% of D = 11.8 min → NOT met (E exceeds by 1.2 min; E = 110% of band)
  vs u_val: 13 min > 9 min → exceeds by 4 min → resolves as model error, actionable finding
  Largest prediction that would have cleared: D + 10%·D = 129.8 min

Two comparisons:
  - Separation (average − single-point crossing): test 163 − 118 = 45 min; run 176 − 131 = 45 min
  - Hot-spot excess over nine-point mean at governance: test 181 − 96 = 85 °C at 118 min;
    run 181.1 − 89.9 = 91 °C (91.2 °C exact) at 131 min
Model diagnosis: offset structure (45-min separation; hot-spot excess 85–91 °C) is preserved; bulk heating
lags (sim nine-point mean 74.6 °C rise vs 96 °C measured at 118 min; 89.9 °C vs 96 °C at the run's
governing moment). Rework belongs to the bulk thermal path (material properties / surface losses, u_inp),
not the tie-bridge detail. No rework started on the file server as of 10/10/2025 (no revised companion
setup, no second run).

Wildfire claim: this exercise establishes only model fidelity against the E119 standard curve (with a
documented +13 min error); it does NOT establish WUI wildfire survival (certification §5.2; Procedure §7).
Gap closes with the physical WUI test — Red Butte confirmatory window 10/27/2025 — and a separate
validation of the SOW §3.1 cases, reported as a signed S, D, E, u_val rollup with D from the physical WUI
test report of record (crossing-time form with units; never yes/no; never an E119-derived or
client-amended figure).

If the 129 min figure is ever substantiated: D = 129 min ≥ 120 min → the 1-hour rating could be reissued
at 2 hours — but only via a Red Butte reissued report (-R1) plus a new Ironwood certification; no other
party may restate the rating (IWFPE-CERT-25-0374 §4). Validation would then read E = +2 min (≤ 12.9 min
criterion, ≤ 9 min u_val). Conditional only; rating of record today remains 1-hour.

Stamp language: "CFD thermal analysis only. Fire-resistance rating certified separately by others."

Checklist disposition: memo CLOSES item 6 (validation as E ± u_val vs criterion, not yes/no).
OPEN: items 2, 3, 4, 5, 7, 9; item 8 already closed (now with the certification citation it awaited);
item 10 (sign-off) open pending the rest. Phase 1 rev B releases only as "with a documented finding."

Phase 1 implications: §7 rewritten to the rollup form; "validated" wording removed; release conditioned on
the documented finding; wildfire claim held for the 10/27/2025 WUI test; no action requested of Red Butte
or Ironwood today.

Paragraph for Bianca (10/10/2025): “Bianca — straight answer, as of 10/10/2025: the E119 companion
simulation is not validated, and we cannot put “validated against the certified test” in Friday’s launch
materials. The run’s governing crossing is 131 min against the certified 118 min, so the model error is
+13 min — outside our 11.8 min acceptance band and outside the ±9 min combined uncertainty; we report it as
a documented finding with a bulk-thermal rework, not as a pass. Your 129 min figure is recorded in our
correspondence file but is not admissible as the experimental value until Red Butte reissues the report
with a calibration certificate, and until then the rating of record stays 1-hour; if it is ever
substantiated, only Ironwood can restate the rating, and the validation would re-run at E = +2 min.
Nothing in this exercise supports a 2-hour or any wildfire figure — the WUI claim needs the 10/27
confirmatory wildfire test, and any future comparison will be reported as a signed error with uncertainty
against a physical WUI report of record, never as a yes/no. Launch copy should say: 1-hour certified rating
(Ironwood, 09/29/2025), E119 model fidelity pending a documented +13 min finding, WUI validation in
progress.”
