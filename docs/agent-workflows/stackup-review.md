# Stackup Review Workflow

## Purpose

Review a KiCad board stackup, check whether it is credible for the intended fabrication service, validate impedance targets with the project calculations, and recommend layer roles and routing arguments.

## Inputs

Required: an input `.kicad_pcb` path.

Optional: intended fabrication service, finished thickness, copper weights, layer count, impedance targets, plane requirements, and official capability data.

This workflow is read-only. Do not directly change the board stackup.

## Procedure

1. Parse and report all copper and dielectric layers, thicknesses, material, and dielectric constants.
2. Classify the current stackup as deliberate, likely default, incomplete, or unknown. Missing data or repeated generic dielectric values require a warning.
3. Gather requirements from verified differential-pair and high-speed analysis. Do not choose final impedance targets solely from net names.
4. When a fabrication service is specified, use its current official stackup and capability documentation. Do not invent core, prepreg, or process values.
5. Recommend signal and plane layer roles with return-path rationale.
6. Validate each target using `calculate_width_for_impedance()` and related project functions on the proposed stackup.
7. Compare calculated geometry against process floors and available routing space. Report infeasible targets and propose a specific alternative.
8. Remind the user that an accepted stackup change invalidates previously calculated impedance widths and time matching.

## Output contract

Provide:

1. Current stackup table and credibility verdict.
2. Source for external fabrication values when used.
3. Recommended stackup and layer-role table.
4. Calculated widths per impedance target and routing layer.
5. Manufacturability verdict and infeasible targets.
6. Resulting `--layers`, `--impedance`, and plane-layer arguments.
7. Optional manual Board Setup guidance.
8. A reminder to rerun impedance- and time-based routing after a stackup change.

Do not modify the board automatically because the stackup is a fabrication-facing design decision.

## Technical reference

Use `.claude/skills/recommend-stackup/SKILL.md` for project API examples and output details. Treat literal `WebSearch` wording as generic web access and prefer primary fabrication sources.
