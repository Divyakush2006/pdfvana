import { useState } from "react";
import { Check, Eye, EyeOff } from "lucide-react";
import type { Option } from "../api";

export type Values = Record<string, any>;

export function defaults(options: Option[]): Values {
  const v: Values = {};
  options.forEach((o) => (v[o.id] = o.default));
  return v;
}

export function visible(o: Option, values: Values) {
  if (!o.show_if) return true;
  return Object.entries(o.show_if).every(([k, allowed]) => allowed.map(String).includes(String(values[k])));
}

export function PositionPicker({ value, onChange, choices }: { value: string; onChange: (v: string) => void; choices: { value: string; label: string }[] }) {
  return (
    <div className="grid w-36 grid-cols-3 gap-1.5 rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-950">
      {choices.map((c) => (
        <button
          key={c.value}
          type="button"
          title={c.label}
          aria-label={c.label}
          aria-pressed={value === c.value}
          onClick={() => onChange(c.value)}
          className={`flex h-8 items-center justify-center rounded-md transition ${
            value === c.value ? "bg-brand-600 shadow" : "bg-white hover:bg-brand-100 dark:bg-slate-800 dark:hover:bg-slate-700"
          }`}
        >
          <span className={`h-2 w-2 rounded-full ${value === c.value ? "bg-white" : "bg-slate-400"}`} />
        </button>
      ))}
    </div>
  );
}

function Password({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input className="input pr-10" type={show ? "text" : "password"} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} autoComplete="new-password" />
      <button type="button" className="absolute inset-y-0 right-0 px-3 text-slate-400 hover:text-slate-600" onClick={() => setShow((s) => !s)} aria-label="Show password">
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export function Field({ o, value, set }: { o: Option; value: any; set: (v: any) => void }) {
  const id = `opt-${o.id}`;
  const label = o.type !== "checkbox" && <label htmlFor={id} className="label">{o.label}</label>;
  const help = o.help && <p className="mt-1.5 text-xs text-slate-500">{o.help}</p>;
  switch (o.type) {
    case "checkbox":
      return (
        <label htmlFor={id} className="flex cursor-pointer items-start gap-3 rounded-xl py-1">
          <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition ${value ? "border-brand-600 bg-brand-600" : "border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-900"}`}>
            {value && <Check className="h-3.5 w-3.5 text-white" strokeWidth={3} />}
          </span>
          <input id={id} type="checkbox" className="sr-only" checked={!!value} onChange={(e) => set(e.target.checked)} />
          <span className="text-sm">
            {o.label}
            {help}
          </span>
        </label>
      );
    case "select":
      if ((o.choices?.length || 0) <= 3 && o.choices!.every((c) => c.label.length < 40) && o.id !== "format") {
        return (
          <div>
            {label}
            <div className="grid gap-2" role="radiogroup">
              {o.choices!.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  role="radio"
                  aria-checked={String(value) === c.value}
                  onClick={() => set(c.value)}
                  className={`rounded-xl border px-3 py-2.5 text-left text-sm transition ${
                    String(value) === c.value
                      ? "border-brand-500 bg-brand-50 font-semibold text-brand-800 ring-1 ring-brand-500 dark:bg-brand-500/10 dark:text-brand-200"
                      : "border-slate-200 hover:border-slate-300 dark:border-slate-700 dark:hover:border-slate-600"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
            {help}
          </div>
        );
      }
      return (
        <div>
          {label}
          <select id={id} className="input" value={String(value ?? "")} onChange={(e) => set(e.target.value)}>
            {o.choices?.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          {help}
        </div>
      );
    case "multiselect": {
      const arr: string[] = Array.isArray(value) ? value : [];
      return (
        <div>
          {label}
          <div className="flex max-h-56 flex-wrap gap-1.5 overflow-auto">
            {o.choices?.map((c) => {
              const on = arr.includes(c.value);
              return (
                <button
                  key={c.value}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set(on ? arr.filter((x) => x !== c.value) : [...arr, c.value])}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                    on ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 hover:border-brand-400 dark:border-slate-700"
                  }`}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
          {help}
        </div>
      );
    }
    case "range":
      return (
        <div>
          <label htmlFor={id} className="label flex justify-between">
            <span>{o.label}</span>
            <span className="font-semibold text-brand-700 dark:text-brand-400">{(o.max ?? 1) <= 1 ? `${Math.round(Number(value) * 100)}%` : Math.round(Number(value))}</span>
          </label>
          <input id={id} type="range" className="w-full accent-brand-600" min={o.min ?? 0} max={o.max ?? 1} step={o.step ?? 0.05} value={Number(value)} onChange={(e) => set(Number(e.target.value))} />
        </div>
      );
    case "number":
      return (
        <div>
          {label}
          <input id={id} type="number" className="input" min={o.min ?? undefined} max={o.max ?? undefined} step={o.step ?? 1} value={value ?? ""} onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} />
          {help}
        </div>
      );
    case "color":
      return (
        <div>
          {label}
          <div className="flex items-center gap-2">
            <input id={id} type="color" className="h-10 w-14 cursor-pointer rounded-lg border border-slate-300 bg-white p-1 dark:border-slate-700 dark:bg-slate-900" value={value} onChange={(e) => set(e.target.value)} />
            <span className="font-mono text-xs text-slate-500">{value}</span>
          </div>
        </div>
      );
    case "position":
      return (
        <div>
          {label}
          <PositionPicker value={value} onChange={set} choices={o.choices || []} />
        </div>
      );
    case "password":
      return (
        <div>
          {label}
          <Password value={value || ""} onChange={set} placeholder={o.placeholder || undefined} />
          {help}
        </div>
      );
    case "textarea":
      return (
        <div>
          {label}
          <textarea id={id} rows={4} className="input" placeholder={o.placeholder || undefined} value={value || ""} onChange={(e) => set(e.target.value)} />
          {help}
        </div>
      );
    default:
      return (
        <div>
          {label}
          <input id={id} type="text" className="input" placeholder={o.placeholder || undefined} value={value ?? ""} onChange={(e) => set(e.target.value)} />
          {help}
        </div>
      );
  }
}

export function OptionsForm({ options, values, setValues, hide = [] }: { options: Option[]; values: Values; setValues: (v: Values) => void; hide?: string[] }) {
  return (
    <div className="space-y-5">
      {options
        .filter((o) => !hide.includes(o.id) && visible(o, values))
        .map((o) => (
          <Field key={o.id} o={o} value={values[o.id]} set={(v) => setValues({ ...values, [o.id]: v })} />
        ))}
    </div>
  );
}
