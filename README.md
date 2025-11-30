# Zoho Creator .ds Export Parser

This project provides Python-based tools for parsing and extracting the structure and logic of a Zoho Creator application from a `.ds` export file. The output is a series of clean JSON files that can be used for documentation, analysis, AI processing, or migration work.

## Features
- Extract forms and form fields
- Extract reports and report fields
- Extract form/report workflows with full Deluge code
- Extract global functions
- Extract pages and embedded ZML-based components
- Produce one JSON file per component type
- Deduplicate form definitions automatically

## Usage
Run the full exporter:

```
python ds_full_export.py --file MyApp.ds --outdir export/
```

Or run individual scripts for forms, reports, workflows, pages, or functions.

## Output Files
- `functions_with_code.json`
- `form_workflows_with_code.json`
- `report_workflows_with_code.json`
- `forms.json`
- `form_fields.json`
- `reports.json`
- `report_fields.json`
- `pages.json`
- `page_components.json`

## License
See the `LICENSE` file for details.
