# Zoho Creator .ds Export Parser

**Turn Zoho Creator `.ds` exports into clean, structured JSON — ready for analysis, documentation, and AI.**

This toolkit parses Zoho Creator export files and extracts application structure, logic, and metadata into easy-to-use JSON files.
Ideal for developers, analysts, and consultants working with complex Creator solutions.

---

## 🚀 Why use this?

Zoho Creator `.ds` files are powerful—but hard to analyze at scale.

This project makes them:

* **Readable** → structured JSON instead of raw DSL
* **Queryable** → easy to inspect, filter, and analyze
* **AI-ready** → perfect input for LLMs and automation
* **Portable** → useful for migration and documentation

---

## ✨ Features

* Extract **forms** and **form fields**
* Extract **reports** and **report fields**
* Extract **form and report workflows** (incl. full Deluge code)
* Extract **global functions**
* Extract **pages and ZML-based components**
* One clean JSON file per component type
* **Robust parsing** (missing sections → no crash, just empty output)
* Consistent and simple output naming

---

## ⚡ Quick Start

Run everything in one command:

```bash
python run_all_exports.py
```

### Default behavior

* Automatically uses the `.ds` file in the current folder (if only one exists)
* Outputs all files to:

```
exports/
```

---

### Optional arguments

```bash
python run_all_exports.py --ds MyApp.ds --outdir exports/
```

---

## 📦 Output

The following files are generated:

* `forms.json`
* `form_fields.json`
* `form_workflows.json`
* `functions.json`
* `reports.json`
* `report_fields.json`
* `report_workflows.json`
* `pages.json`
* `page_components.json`

---

## 🧠 Use Cases

* System documentation
* Impact analysis and refactoring
* Data modeling and architecture insight
* AI/LLM processing (RAG, code understanding, automation)
* Migration between environments or platforms

---

## 🛠 Run individual scripts

Example:

```bash
python ds_forms_export.py --file MyApp.ds --out forms.json
```

---

## ⚠️ Notes

* If a section (e.g. pages or workflows) is missing in the `.ds` file:

  * The script will **not fail**
  * Output will be an empty list (`[]`)
* Designed for real-world `.ds` files with inconsistent structure

---

## 📄 License

See the LICENSE file for details.

