# RevB-P4 manufacturing preflight — HOLD / DO NOT ORDER

This is the draft output for the power-sequencing ECO, PCB SHA-256
`19c24b7b0cacdd23822d85daa3e44d5104a866f5a9f83ac38824fee33554cd69`.
The editable P4 project and the [full ECO review](../../QA/power-eco-review.md)
are the current handoff. The P3 preflight directory remains a historical baseline.

## Checks completed

- 337 footprints, 316 SMT placements; native DRC errors / unconnected / ERC / parity: **0 / 0 / 0 / 0**.
- Two existing J1 silk-edge warnings remain; native rules were not relaxed.
- All original 273 placements and 64 local feedback/decoupling paths retained.
- Eleven Gerber layers, four copper layers; closed board outline **110 × 100 mm**.
  The 110.05 × 100.05 gbrjob extent includes the outline stroke.
- **545 drill hits**: 483 through vias + 58 plated component holes + 4 NPTH.
  Plating, diameter and position matched bijectively within 0.000501 mm export precision.
- **1,031 unique ref/pin identities**, corresponding to 1,032 physical numbered pads
  (J1 SH is duplicated), matched the Gerber X2 pad/net attributes with no differences.
  This is not independent image-based copper connectivity extraction.
- All **316 SMT** source codes and exact model names match the supplier results
  (38 distinct codes). `analysis/jlc-live-responses.json` preserves timestamped responses.
- Generic libngspice DC/AC and digital state regression completed; updated eight-channel
  firmware compiled successfully and was not uploaded.

## Remaining release holds

1. J1 horizontal DB25 actual MPN, vendor drawing and cable/mechanical fit are pending.
2. CS42448-CQZR / C2151089 stock is **0**. ADG4613BRUZ / C657392 stock is **15**,
   with five required per board; availability is an observation, not a reservation.
3. `JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv` preserves native KiCad rotations.
   Confirm library pin-1/package orientation in the assembly preview before release.
4. No bench power-ramp/leakage, precision DC calibration, cable stability, full short-circuit
   thermal or EMC qualification. ADG capacitance has no maximum bound in the cited table;
   exact negative-signal shutdown leakage remains a qualification gap.

## Evidence and interpretation

`frozen/` and `input-manifest.json` bind the design inputs. `review-receipt.json`
binds the draft outputs, review, exact-source checks and HOLD verdict.
`analysis/` includes raw schematic, full PCB, cross-analysis, cross-verification,
Gerber, thermal and lifecycle outputs, manufacturer PDF evidence, source delta,
native consistency audit and model results. See `analysis/review-triage.json`:
the two reported connectivity splits were checked against native copper geometry;
generic analog-pair skew limits and different-layer bounding extents are not
accepted as disconnected copper or displaced exports.

Thermal automation assessed zero components (SKIPPED); all 40 lifecycle statuses
are unknown. The EMC-specific 44-rule tool is unavailable. These gaps are explicit
in the full review. Evidence-gate partial checks do not imply electrical qualification.

## Files

- `gerbers-DRAFT/`: native 11-layer Gerbers, separate PTH/NPTH drills and drill maps.
- `assembly-DRAFT/JLC_BOM_DRAFT.csv`: 316 SMT parts grouped for assembly.
- `assembly-DRAFT/JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv`: 316 Top placements.
- `assembly-DRAFT/rotation-audit.json`: pad-1 geometry for orientation review.
- `analysis/drill-readback.json`, `gerber-pin-readback.json`, `jlc-source-audit.json`.
- `analysis/power-eco-verification.json`: current P4 models; historical P3 model
  outputs must not be substituted.

No fabrication/assembly release, order submission or firmware upload has been made.
Any design change requires fresh native checks, exports and hash-bound readback.
