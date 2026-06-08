# doc_compiler

Compiles your structured Markdown API specs into **one IR**, and derives everything
downstream from it. The Markdown docs are the single source of truth — no API name,
field name, enum, or stage assignment is hand-maintained anywhere else.

```
api_docs/*.md  ──►  compiler.py  ──►  kb_ir.json               (single source of truth)
                                  ├─► catalog.json / catalog.md (Stage-1 selection menu)
                                  ├─► context_spec.md           (Generator full-context payload)
                                  └─► models_jsonschema.json    (Reviewer validation + structured output)
```

## Run

```bash
pip install pydantic
python compiler.py --docs ./api_docs --out ./compiled            # parse + lint(warn) + emit all
python compiler.py --docs ./api_docs --lint --strict             # CI gate: warnings -> exit 1
python compiler.py --docs ./api_docs --out ./compiled --emit ir,catalog,context,models
```

`compiled_example/` is the output of running against `api_docs_fixture/` so you can see the
shape of each artifact. Point `--docs` at your real `api_docs/` and it runs unchanged.

## Doc template the linter enforces

Two new front-matter lines are the only authoring change vs. your current docs. Both are
read from blockquotes right under the Endpoint bullets:

```markdown
# Segment_ROI_API_v10 参数说明

- **Endpoint**: `POST /api/v10/segment-roi/run`
- **Content-Type**: `application/json`

> 用途: <one line: WHEN/WHY you'd reach for this API — the discriminating intent>
> 阶段: segment        # deconvolve | segment | target | measure | calculate | render | shared

## 1. 功能说明
...
## 8. cellpose: run_segmentation 请求参数
| 参数名 | 类型 | 必填 | 枚举值/允许值 | 说明 |
|---|---:|:---:|---|---|
| `params.cellposeParams.diameter` | number | 是 | >0 | ... |
```

- **`> 用途:`** is the catalog one-liner. It's what the model reads at selection time, so it
  should encode the *discriminating* intent (when you'd pick this over a sibling), not just a
  restatement of the name. If absent, the compiler falls back to the first sentence of 功能说明
  and emits a WARN.
- **`> 阶段:`** assigns the pipeline stage. If absent, a migration-only fallback map infers it
  and emits a loud WARN. `shared` is the cross-cutting bucket (Put/Get_File, Get_Target, etc.).
- Everything else is your existing format: H1 `… 参数说明` title, `- **Endpoint**` bullets,
  numbered `… 请求参数` sections, and `参数名 | 类型 | 必填 | 枚举值/允许值 | 说明` tables.
  Dotted paths (`params.cellposeParams.flowThreshold.min`) and `array<object>` with `[]`
  children are reconstructed into nested schemas. Response tables (`… 响应参数`) are ignored
  for request models and the context spec.

## How each artifact is consumed

| Artifact | Consumer | Role |
|---|---|---|
| `kb_ir.json` | everything | the compiled source of truth; all other outputs are views over it |
| `catalog.md` / `.json` | Generator (Stage-1) | the always-in-context menu the model selects from |
| `context_spec.md` | Generator | dense full-context payload (boilerplate stripped) at small scale |
| `models_jsonschema.json` | Reviewer + structured output | per-(api, method:operation) JSON Schema |

The per-group JSON Schemas are usable two ways from one artifact: load them into Pydantic for
the Reviewer's deterministic validation, and hand the relevant one to the model's structured-output
mode so it cannot emit a field or enum outside the schema.

## Known v1 limitations (documented, not bugs)

- A nested container that appears only inside a branch table with no row of its own defaults to
  `required`. In practice that container also has a `否` row in the 通用 table; the Reviewer composes
  `通用 (common) + branch`, and optionality comes from the common group. Compose before validating.
- Loose numeric constraints (`>0`, `1~类别数`) are kept as description hints, not hard validators.
- Method/operation are parsed from headers of the form `<method>: <operation> 请求参数`. Other
  shapes still parse as a single group keyed by the cleaned header label.
