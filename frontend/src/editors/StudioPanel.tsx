import { useState } from "react";
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import type { Choice, Option } from "../api";
import { Field, type Values } from "../components/OptionsForm";
import { useApp } from "../store";

type StepField = Partial<Option> & { id: string; label: string; type: Option["type"] };
type StepDef = { label: string; hint: string; fields: StepField[] };

const ch = (...p: string[]): Choice[] => p.reduce<Choice[]>((a, v, i) => (i % 2 ? a : [...a, { value: v, label: p[i + 1] }]), []);

function stepDefs(langs: Choice[]): Record<string, StepDef> {
  return {
    compress: {
      label: "Compress", hint: "Shrink file size",
      fields: [
        { id: "level", label: "Level", type: "select", default: "recommended", choices: ch("light", "Light", "recommended", "Recommended", "strong", "Strong", "extreme", "Extreme", "target", "Target size") },
        { id: "target_mb", label: "Target MB", type: "number", default: 1, step: 0.1, min: 0.05, show_if: { level: ["target"] } },
      ],
    },
    ocr: { label: "OCR", hint: "Make scanned pages searchable", fields: [{ id: "languages", label: "Languages", type: "multiselect", default: ["eng"], choices: langs }] },
    watermark: {
      label: "Watermark", hint: "Stamp text over pages",
      fields: [
        { id: "text", label: "Text", type: "text", default: "CONFIDENTIAL" },
        { id: "opacity", label: "Transparency", type: "range", default: 0.2, min: 0.05, max: 1, step: 0.05 },
        { id: "mosaic", label: "Repeat across page", type: "checkbox", default: false },
      ],
    },
    page_numbers: {
      label: "Page numbers", hint: "Number every page",
      fields: [
        { id: "format", label: "Format", type: "select", default: "Page {n} of {total}", choices: ch("{n}", "1", "Page {n}", "Page 1", "{n} / {total}", "1 / 10", "Page {n} of {total}", "Page 1 of 10") },
        { id: "position", label: "Position", type: "select", default: "bottom-center", choices: ch("bottom-center", "Bottom centre", "bottom-right", "Bottom right", "bottom-left", "Bottom left", "top-right", "Top right", "top-center", "Top centre") },
      ],
    },
    header_footer: {
      label: "Header & footer", hint: "Text on every page",
      fields: [
        { id: "header", label: "Header", type: "text", default: "" },
        { id: "footer", label: "Footer", type: "text", default: "" },
      ],
    },
    rotate: { label: "Rotate", hint: "Turn pages", fields: [{ id: "angle", label: "Angle", type: "select", default: "90", choices: ch("90", "90° right", "180", "180°", "270", "90° left") }] },
    remove_pages: { label: "Remove pages", hint: "Drop pages you don't need", fields: [{ id: "pages", label: "Pages", type: "text", default: "", placeholder: "e.g. 2, 5-7" }] },
    grayscale: { label: "Grayscale", hint: "Convert colours to grey", fields: [] },
    flatten: { label: "Flatten", hint: "Lock forms & annotations", fields: [] },
    sanitize: { label: "Sanitize", hint: "Strip metadata & scripts", fields: [] },
    protect: { label: "Password protect", hint: "AES-256 (PDF output)", fields: [{ id: "password", label: "Password", type: "password", default: "" }] },
  };
}

export type Step = { op: string } & Values;

const asOption = (f: StepField): Option => ({ default: null, choices: null, help: null, min: null, max: null, step: null, placeholder: null, show_if: null, ...f }) as Option;

export function StudioPanel({ values, setValues }: { values: Values; setValues: (v: Values) => void }) {
  const { catalog } = useApp();
  const defs = stepDefs(catalog?.ocr_languages || [{ value: "eng", label: "English" }]);
  const [adding, setAdding] = useState(false);
  const steps: Step[] = (() => {
    try {
      return JSON.parse(values.steps || "[]");
    } catch {
      return [];
    }
  })();
  const setSteps = (s: Step[]) => setValues({ ...values, steps: JSON.stringify(s) });
  const studio = catalog?.tools.find((t) => t.id === "studio");
  const allowed = new Set((studio?.options.find((o) => o.id === "format")?.choices || []).map((c) => c.value));
  const formats = Object.entries(catalog?.formats || {}).filter(([k]) => allowed.has(k)).map(([k, f]) => [k, f.label] as const);

  const addStep = (op: string) => {
    const d = defs[op];
    const s: Step = { op };
    d.fields.forEach((f) => (s[f.id] = f.default));
    setSteps([...steps, s]);
    setAdding(false);
  };
  const move = (i: number, d: number) => {
    const n = [...steps];
    [n[i], n[i + d]] = [n[i + d], n[i]];
    setSteps(n);
  };

  return (
    <div className="space-y-6">
      <Field o={asOption({ id: "merge", label: "Merge everything into one document", type: "checkbox" })} value={values.merge} set={(v) => setValues({ ...values, merge: v })} />

      <div>
        <div className="label">Steps <span className="font-normal text-slate-400">(applied in order)</span></div>
        <ol className="space-y-2">
          {steps.map((s, i) => {
            const d = defs[s.op];
            if (!d) return null;
            return (
              <li key={i} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">{i + 1}</span>
                  <span className="flex-1 text-sm font-semibold">{d.label}</span>
                  <button className="btn-ghost p-1" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up"><ArrowUp className="h-3.5 w-3.5" /></button>
                  <button className="btn-ghost p-1" disabled={i === steps.length - 1} onClick={() => move(i, 1)} aria-label="Move down"><ArrowDown className="h-3.5 w-3.5" /></button>
                  <button className="btn-ghost p-1 hover:text-red-600" onClick={() => setSteps(steps.filter((_, j) => j !== i))} aria-label="Remove step"><X className="h-3.5 w-3.5" /></button>
                </div>
                {d.fields.length > 0 && (
                  <div className="mt-3 space-y-3">
                    {d.fields
                      .filter((f) => !f.show_if || Object.entries(f.show_if).every(([k, v]) => v.includes(s[k])))
                      .map((f) => (
                        <Field key={f.id} o={asOption(f)} value={s[f.id]} set={(v) => setSteps(steps.map((x, j) => (j === i ? { ...x, [f.id]: v } : x)))} />
                      ))}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
        {adding ? (
          <div className="mt-2 grid grid-cols-2 gap-1.5 rounded-xl border border-slate-200 p-2 dark:border-slate-700">
            {Object.entries(defs).map(([op, d]) => (
              <button key={op} onClick={() => addStep(op)} className="rounded-lg p-2 text-left hover:bg-brand-50 dark:hover:bg-brand-500/10">
                <div className="text-sm font-semibold">{d.label}</div>
                <div className="text-[11px] text-slate-500">{d.hint}</div>
              </button>
            ))}
          </div>
        ) : (
          <button className="btn-outline mt-2 w-full border-dashed" onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" /> Add a step
          </button>
        )}
      </div>

      <div>
        <div className="label">Export as</div>
        <div className="grid grid-cols-3 gap-1.5">
          {formats.map(([k, label]) => (
            <button
              key={k}
              onClick={() => setValues({ ...values, format: k })}
              title={label}
              className={`rounded-lg border px-2 py-2 text-xs font-semibold transition ${values.format === k ? "border-brand-600 bg-brand-600 text-white" : "border-slate-200 hover:border-brand-400 dark:border-slate-700"}`}
            >
              {k === "pdfa" ? "PDF/A" : k.toUpperCase()}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-slate-500">{catalog?.formats[values.format]?.label}</p>
      </div>

      {["jpg", "png", "webp", "tiff"].includes(values.format) && (
        <Field o={asOption({ id: "dpi", label: "Image resolution (DPI)", type: "number", min: 72, max: 600 })} value={values.dpi} set={(v) => setValues({ ...values, dpi: v })} />
      )}
      <Field
        o={asOption({ id: "normalize", label: "Page size", type: "select", choices: ch("none", "Keep original sizes", "a4", "Make all A4", "letter", "Make all Letter", "first", "Match first page") })}
        value={values.normalize}
        set={(v) => setValues({ ...values, normalize: v })}
      />
      <Field o={asOption({ id: "output_name", label: "Output file name", type: "text", placeholder: "merged" })} value={values.output_name} set={(v) => setValues({ ...values, output_name: v })} />
    </div>
  );
}
