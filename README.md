# PipeFlow PG Bible Export

This export creates a single-sheet PG Bible workbook from the bundled May 2026 PG Bible template.

## Setup

```bash
python3 -m pip install -r requirements.txt
```

## API mode

Set the API environment variables:

```bash
export PIPEFLOW_BASE_URL="http://localhost:5050"
export PIPEFLOW_API_TOKEN="your-token"
export PG_BIBLE_TEMPLATE_PATH="/path/to/PGBible_Template_May2026.xlsx"
```

Run:

```bash
python3 main.py --api --template "/path/to/PGBible_Template_May2026.xlsx" --output-dir outputs
```

API endpoint paths are isolated in `pipeflow_client.py` until the PipeFlow API contract is final.

## JSON mode

```bash
python3 main.py --json sample_report.json --template "/path/to/PGBible_Template_May2026.xlsx" --output-dir outputs
```

Expected top-level keys:

- `profile`
- `calc_payload`
- `plan_items`
- `action_items`
- `weekly_results`

`calc_payload` must include:

- `starting_pipeline`
- `pipeline_added`
- `pipeline_target`

## PipeFlow app export button

The Reports page includes `Export PG Bible`.

The local app route reads the template path from `PG_BIBLE_TEMPLATE_PATH`. If it is not set, it uses the bundled `pg_bible_templates/PGBible_Template_May2026.xlsx` file.

PG GOALS inputs are deliberately explicit. Set these before starting the app if you want the button to generate the workbook from local PipeFlow data:

```bash
export PIPEFLOW_PG_STARTING_PIPELINE="6800000"
export PIPEFLOW_PG_PIPELINE_ADDED="11200000"
export PIPEFLOW_PG_PIPELINE_TARGET="27200000"
```

If `PIPEFLOW_PG_STARTING_PIPELINE` or `PIPEFLOW_PG_PIPELINE_ADDED` is missing, the export fails with `CALC_INPUT_MISSING` rather than guessing business rules.

## CSV mode

```bash
python3 main.py --csv sample_report.csv --template "/path/to/PGBible_Template_May2026.xlsx" --output-dir outputs
```

CSV rows use `record_type` with these values:

- `profile`
- `calc`
- `plan`
- `action`
- `weekly_result`

## Validation

The exporter fails hard if:

- The `Real example` sheet is missing.
- Required PG sections are missing.
- Required table headers cannot be found.
- Weekly key discovery is ambiguous.
- Calculation inputs are missing.
- A write would exceed a detected boundary.
- Merges, column widths, row heights, or protected header strings differ from the cloned template after export.

The output file is named `PGBible_<username>.xlsx`. The workbook contains exactly one worksheet named from the PipeFlow profile name, with Excel-safe sanitisation.
