# Calculation reliability

The supported prompt `Solve dy/dx = a*x+b with y(x0) = y0` with explicit
integration/initial-condition/differentiation instructions uses polynomial
integration and checks both the derivative and initial condition in code. The
registry/sensor/maintenance overview for a single equipment ID uses guarded
read-only SQL, counts each distinct registered dataset and sums actual row counts.
Neither path needs model inference or invented data. Run
`scripts/measure/recording_smoke.py --env-file <existing configuration>` to check
the two recording prompts against the connected database without persistent memory
writes. This does not establish arbitrary engineering-prompt accuracy: the live
4B model still failed the beam fixture, while the new checks prevented accepting
its unsupported answer.

Prompts of the supported form `Solve <one linear equation> for x` also use a bounded
code path. Linearity is checked structurally and the answer is checked by
substitution. Unsupported and nonlinear forms stay on the normal expert path.

The reported beam failure returned a reference example's 75 without a valid
calculation. For the actual inputs the rectangular-section formula is
`sigma = 6*F*L/(b*h**2)`, giving `45 MPa` for `F=500 N`, `L=0.3 m`,
`b=0.05 m`, `h=0.02 m`. This assumes the stated bending axis, linear elasticity
and ideal fixed support; it is not a complete beam design check.

## Shared behavior

Euler and the configurable experts share a scalar calculator. A physical call can
provide named inputs and a requested output unit:

```json
{
  "expr": "6*F*L/(b*h**2)",
  "inputs": {
    "F": {"value": 500, "unit": "N"},
    "L": {"value": 0.3, "unit": "m"},
    "b": {"value": 0.05, "unit": "m"},
    "h": {"value": 0.02, "unit": "m"}
  },
  "unit": "MPa"
}
```

Named input quantities must match the task or accepted dependency context.
Simple literal substitutions also infer units from unambiguous supplied magnitudes;
named inputs are required for ambiguous equal magnitudes. Typed SQL column units
are retained for common columns such as `mass_kg`. References are supplied separately
and cannot supply numerical proof or replace missing task inputs.

Outputs record value, unit, input quantities and Pint version. The interpreter
allows scalar arithmetic and selected math functions, with length, node, nesting,
exponent and finite-result checks. Powers accept `**` or `^`. The quantity evaluator
uses a cooperative time limit; this is not process isolation. It cannot execute
Python attributes, imports, subscripts or arbitrary functions.

Euler's physical/reference calculation answers are assembled from successful
calculator outputs. Scalar answers that omit the computed result are corrected
from that result. Configurable experts also correct physical answers that omit
the computed result. Signs, displayed rounding and compatible unit conversions
are checked. Final answers containing typed calculations are assembled from
accepted results by code; reference-only example prose is omitted from that answer
while inherited source citations are retained. Source hashes, versions, confidence and failed expression inputs
are excluded from numerical proof. Failed calculations prevent completion even
when another tool succeeded. A reviewer exception, unreadable verdict or unresolved
negative review cannot silently approve an answer or persist it as a finding.

## Limits

These checks establish execution of the selected arithmetic and unit consistency.
They do not prove the model selected the right formula, assigned equal-unit inputs
to the right variables, addressed every part of a question, or used valid physical
assumptions. Plain-text quantity extraction and requested-dimension recognition
cover common notation, not every natural-language prompt. Missing constants must
be supplied explicitly. Physical/reference results remain excluded from persistent
validated findings. Some prompts may now return an unfinished task instead of an
unsupported numerical answer.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests --ignore=tests/test_integration.py --ignore=tests/test_markovian.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_markovian.py -k "not reference_engine"
.\.venv\Scripts\python.exe scripts/measure/knowledge_smoke.py
.\.venv\Scripts\python.exe scripts/measure/calculation_eval.py
```

The smoke uses scripted model replies and deliberately supplies a copied 75 MPa
answer alongside the correct changed-input calculation. The regression suite
also replays the failed live expression and tests reviewer failures, signed
values, conversion, missing inputs and scalar answer substitution.

With an authorized provider configured, `calculation_eval.py --live` exercises
real model planning, execution, review and composition. `--only beam,algebra,missing_inputs`
selects a small run. `--env-file` loads an existing configuration without copying
or printing its credentials; `--output` writes a measurement report. It uses
temporary indexes/traces and fresh in-memory findings, and does not restart or
deploy the webpage. A passing finite fixture set does not establish accuracy on
arbitrary prompts.
