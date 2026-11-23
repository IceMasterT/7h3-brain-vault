---
type: project
status: active
created: 2026-11-23
updated: 2026-11-23
summary: AFPMG Rev G-A1 is the leading 98% shaft-to-DC generator concept, re-sized from Rev 3.1 with a calibrated loss model and a parametric 3D model.
tags: [afpmg, generator, axial-flux, engineering]
aliases: [AFPMG Rev G, Rev G-A1]
source: AFPMG Rev 3 and Rev 3.1 build specifications and drawing sets, 98pct Master Engineering Dossier, 98pct Round Table Executive Review (user uploads, 2026-11-23)
confidence: medium
---
# AFPMG Rev G-A1

## Goal
Reach at least 98.0% continuous shaft-to-regulated-48 V DC efficiency at 2,400 W (loss at most 48.98 W), with 3,000 W at 98% as the second objective (at most 61.22 W). Source: 98pct Master Engineering Dossier.

## Status
Where I paused: analytical design and concept 3D model done. No FEA, no coupon, no hardware. Not a release drawing.

Result from the calibrated model (inferred: model output, not measured):
| Design | 2.4 kW loss | eta 2.4 kW | 3 kW loss | eta 3 kW |
|---|---|---|---|---|
| Rev 3.1 reproduced | 132.6 W | 94.77% | 191.4 W | 94.00% |
| G-A1, G-series converter | 52.2 W | 97.87% | 66.6 W | 97.83% |
| G-A1, stretch converter | 47.9 W | 98.04% | 60.8 W | 98.02% |
| G-B 16/12, same envelope | 54.8 W | 97.77% | 69.9 W | 97.72% |
| G-C 2 stators, 3 rotors | 53.8 W | 97.81% | 68.4 W | 97.77% |

The model reproduces the Rev 3.1 specification's own figures (133 W, 94.75%) within 0.5 W before any change is applied.

## G-A1 design values
- 12 poles, 9 coils, single coreless stator, two steel-backed rotors, 2,400 RPM, 240 Hz.
- Magnet annulus r 75 to 126 mm, 12.0 mm thick, Br 1.42 T class (N50SH), 24 segments, 4.9 kg.
- Stator 14.0 mm, 1.4 mm air gap each side, 16.8 mm magnetic gap, spacer 36.8 mm.
- 4 turns per coil, 0.10 mm Litz (about 1,650 strands per turn), 2.17 mOhm per phase at 80 C including bus.
- Cold line-to-line EMF 28.65 V rms at 2,400 RPM, same AFE headroom rule as Rev 3.1.
- Rotor discs AISI 1018, D260 x 16 mm, 13 mm iron under magnets (1.25 T). Axial pull 5.2 kN, closed through the spacer.
- 2 x 6005 hybrid bearings with wave-spring preload. Close-clearance windage shroud.
- Integrated AFE on the collar: 3 x 100 V MOSFET per switch, 20 kHz, 0.35 mOhm inductors. Stretch version: 5 per switch, 16 kHz.

## Findings
- G-A beats G-C here: extra rotor faces add windage that cancels the copper gain. Inferred from the model.
- After copper is fixed, windage (11.7 W) and converter (13.6 W) set the floor.
- 98% margin with the stretch converter is 1.05 W at 2.4 kW and 0.47 W at 3 kW, smaller than the windage uncertainty (+50% windage adds 5.9 W).
- Source error: the Rev 3.1 text gives 2.05 mWb flux per pole; its own 0.742 T face field gives 1.23 mWb, which matches its 1.25 T back-iron figure.

## Next step
3D magnetostatic FEA of one pole pair at 16.8 mm gap, then a windage spin-down of a dummy D260 rotor pair with the shroud.

## Constraints and decisions
- Speed held at 2,400 RPM and the 48 to 56.8 V bus held, as in Rev 3.1.
- No production release until the dossier's gates 01 to 06 pass.

## Files
- model/afpmg_model.py: calibrated loss model. model/final_design.py prints every number above.
- model/sweep.py, pareto.py, fine.py: design-space search (59,040 geometries, then integer turns).
- cad/afpmg_cad.py: parametric 3D generator. Outputs afpmg-rev-ga1.glb (33 parts) and afpmg-rev-ga1-assembly.stl (mm).
- viewer/index.html: interactive viewer, published as a private artifact: https://claude.ai/artifact/4zvTwjJtcWQyoB7kEeQpeE

## Log
- 2026-11-23 Consolidated Rev 3, Rev 3.1, dossier and round table. Built calibrated model, chose G-A1, generated 3D model and viewer.

## Related
- [[now]]
- [[index]]
