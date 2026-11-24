import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, ChevronDown, ChevronLeft, Clock, Globe, ImagePlus, Loader2, Lock, ShieldCheck, Sparkles, X } from "lucide-react";
import { allowedTargets, createJob, getJob, setHead, type Catalog, type JobState, type Seo, type Tool } from "../api";
import { Dropzone, FileGrid, filterAccepted, toItems, type FileItem } from "../components/Files";
import { OptionsForm, defaults, type Values } from "../components/OptionsForm";
import { ErrorView, ProcessingView, ResultView } from "../components/Progress";
import { OrganizeEditor, type PageItem } from "../editors/OrganizeEditor";
import { SignEditor, type Placement } from "../editors/SignEditor";
import { StudioPanel } from "../editors/StudioPanel";
import { ToolIcon } from "../icons";
import { useApp } from "../store";
import NotFound from "./NotFound";

type Phase = "edit" | "uploading" | "processing" | "done" | "error";
type Setup = { tool: Tool; seo: Seo; preset: Values; accept: string[]; key: string };

const CATEGORY_ORDER: [string, string][] = [["document", "Documents"], ["image", "Images"], ["data", "Data"], ["audio", "Audio"], ["video", "Video"]];

function resolve(catalog: Catalog, slug: string): Setup | null {
  const tool = catalog.tools.find((t) => t.id === slug);
  if (tool) return { tool, seo: tool.seo, preset: {}, accept: tool.accept, key: tool.id };
  const pair = catalog.pairs.find((p) => p.slug === slug);
  const convert = catalog.tools.find((t) => t.id === "convert");
  if (pair && convert) return { tool: convert, seo: pair, preset: { format: pair.to }, accept: pair.accept, key: pair.slug };
  return null;
}

export default function ToolPage() {
  const { toolId = "" } = useParams();
  const { catalog, error, takeHandoff } = useApp();
  const setup = useMemo(() => (catalog ? resolve(catalog, toolId) : null), [catalog, toolId]);
  if (!catalog)
    return (
      <div className="flex flex-col items-center py-32 text-center text-slate-500">
        <Loader2 className="mb-4 h-8 w-8 animate-spin text-brand-600" />
        {error || "Loading tools…"}
      </div>
    );
  if (!setup) return <NotFound />;
  return <ToolWorkspace key={setup.key} setup={setup} catalog={catalog} takeHandoff={takeHandoff} />;
}

function TrustRow({ ttl }: { ttl: number }) {
  return (
    <div className="mt-6 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-slate-500">
      <span className="flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Files deleted after {Math.round(ttl / 60)} minutes</span>
      <span className="flex items-center gap-1.5"><Lock className="h-3.5 w-3.5" /> Encrypted transfer</span>
      <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> No sign-up, no watermarks</span>
    </div>
  );
}

function SeoSection({ seo }: { seo: Seo }) {
  return (
    <section className="mx-auto mt-20 max-w-3xl" aria-labelledby="howto">
      <h2 id="howto" className="text-2xl font-bold tracking-tight">How to use {seo.h1}</h2>
      <ol className="mt-5 grid gap-3 sm:grid-cols-3">
        {seo.steps.map((s, i) => (
          <li key={i} className="card p-4 text-sm text-slate-600 dark:text-slate-300">
            <span className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">{i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      <h2 className="mt-14 text-2xl font-bold tracking-tight">Frequently asked questions</h2>
      <div className="mt-5 divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
        {seo.faqs.map((f) => (
          <details key={f.q} className="group px-5 py-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
              {f.q}
              <ChevronDown className="h-4 w-4 shrink-0 text-slate-400 transition group-open:rotate-180" />
            </summary>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{f.a}</p>
          </details>
        ))}
      </div>
      {seo.related && (
        <Link
          to={`/${seo.related.slug}`}
          className="card mt-8 flex items-center justify-between gap-4 p-5 transition hover:border-brand-300 hover:shadow-md"
        >
          <span>
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500">Need more options?</span>
            <span className="mt-1 block font-semibold">Try {seo.related.name}</span>
          </span>
          <ArrowRight className="h-5 w-5 shrink-0 text-brand-600" />
        </Link>
      )}
    </section>
  );
}

function FormatPicker({ catalog, names, value, onChange }: { catalog: Catalog; names: string[]; value: string; onChange: (v: string) => void }) {
  const allowed = new Set(allowedTargets(catalog, names));
  return (
    <div className="space-y-4">
      {CATEGORY_ORDER.map(([cat, label]) => {
        const formats = Object.entries(catalog.formats).filter(([k, f]) => f.category === cat && allowed.has(k));
        if (!formats.length) return null;
        return (
          <div key={cat}>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</div>
            <div className="grid grid-cols-4 gap-1.5">
              {formats.map(([k, f]) => (
                <button
                  key={k}
                  type="button"
                  title={f.label}
                  aria-pressed={value === k}
                  onClick={() => onChange(k)}
                  className={`rounded-lg border px-1.5 py-2 text-xs font-bold transition ${value === k ? "border-brand-600 bg-brand-600 text-white shadow" : "border-slate-200 hover:border-brand-400 dark:border-slate-700"}`}
                >
                  {k === "pdfa" ? "PDF/A" : k.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        );
      })}
      {allowed.size === 0 && <p className="text-sm text-amber-700">These files can't be converted together. Convert them separately.</p>}
    </div>
  );
}

function ToolWorkspace({ setup, catalog, takeHandoff }: { setup: Setup; catalog: Catalog; takeHandoff: () => File[] }) {
  const { tool, seo, preset, accept } = setup;
  const ttl = catalog.limits.ttl_seconds;
  const [items, setItems] = useState<FileItem[]>([]);
  const [values, setValues] = useState<Values>(() => ({ ...defaults(tool.options), ...preset }));
  const [extras, setExtras] = useState<Record<string, File | null>>({});
  const [phase, setPhase] = useState<Phase>("edit");
  const [upload, setUpload] = useState(0);
  const [job, setJob] = useState<JobState | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const layout = useRef<PageItem[]>([]);
  const placement = useRef<Placement | null>(null);
  const poll = useRef<number | null>(null);

  useEffect(() => {
    const canonical = `${catalog.site.replace(/\/$/, "")}/${setup.key}`;
    setHead(seo.title, seo.description, canonical);
    const handed = takeHandoff();
    if (handed.length) addFiles(handed);
    return () => {
      if (poll.current) window.clearTimeout(poll.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addFiles = useCallback(
    (files: File[]) => {
      const { ok, rejected } = filterAccepted(files, accept);
      setNotice(rejected.length ? `${rejected.map((f) => f.name).join(", ")} can't be used with ${seo.h1}.` : "");
      if (!ok.length) return;
      setItems((cur) => {
        const limit = tool.max_files || catalog.limits.max_files;
        const next = tool.multiple ? [...cur, ...toItems(ok)] : toItems(ok.slice(0, 1));
        if (next.length > limit) setNotice(`You can use up to ${limit} files with this tool.`);
        return next.slice(0, limit);
      });
    },
    [tool, accept, catalog, seo.h1],
  );

  // Keep the universal converter's target valid for the files that were added.
  useEffect(() => {
    if (tool.ui !== "convert" || !items.length) return;
    const allowed = allowedTargets(catalog, items.map((i) => i.file.name));
    if (allowed.length && !allowed.includes(values.format)) setValues((v) => ({ ...v, format: allowed[0] }));
  }, [items, tool.ui, catalog, values.format]);

  useEffect(() => {
    if (phase !== "edit") return;
    const over = (e: DragEvent) => e.preventDefault();
    const drop = (e: DragEvent) => {
      e.preventDefault();
      const f = Array.from(e.dataTransfer?.files || []);
      if (f.length) addFiles(f);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [phase, addFiles]);

  const onLayout = useCallback((l: PageItem[]) => {
    layout.current = l;
  }, []);
  const onPlacement = useCallback((p: Placement) => {
    placement.current = p;
  }, []);
  const onSignature = useCallback((f: File | null) => setExtras((e) => ({ ...e, signature: f })), []);

  const blocking = useMemo(() => {
    if (tool.ui === "url") return !(String(values.url || "").trim() || items.length) ? "Enter a web address or add an HTML file" : "";
    if (items.length < Math.max(1, tool.min_files)) return tool.min_files > 1 ? `Add at least ${tool.min_files} files` : "Add a file";
    for (const ex of tool.extra_files) if (ex.required && !extras[ex.id]) return tool.ui === "sign" ? "Create your signature first" : `Add the ${ex.label.toLowerCase()}`;
    if (tool.id === "add-watermark" && values.kind === "image" && !extras.image) return "Choose a watermark image";
    if (tool.id === "protect-pdf" && (!values.password || values.password !== values.confirm)) return values.password ? "Passwords don't match" : "Enter a password";
    if (tool.ui === "convert" && !allowedTargets(catalog, items.map((i) => i.file.name)).includes(values.format)) return "Choose an output format";
    return "";
  }, [tool, items, extras, values, catalog]);

  const run = async () => {
    if (blocking) return;
    const opts: Values = { ...values };
    if (tool.ui === "organize") opts.layout = JSON.stringify(layout.current.map(({ p, r }) => ({ p, r })));
    if (tool.ui === "sign" && placement.current) Object.assign(opts, placement.current);
    setPhase("uploading");
    setUpload(0);
    setError("");
    try {
      const j = await createJob(tool.id, items.map((i) => i.file), opts, extras, setUpload);
      setJob(j);
      setPhase("processing");
      let delay = 500;
      const tick = async () => {
        try {
          const s = await getJob(j.id);
          setJob(s);
          if (s.status === "done") return setPhase("done");
          if (s.status === "error") {
            setError(s.error);
            return setPhase("error");
          }
          delay = Math.min(2000, delay * 1.15);
          poll.current = window.setTimeout(tick, delay);
        } catch (e: any) {
          setError(e.message);
          setPhase("error");
        }
      };
      tick();
    } catch (e: any) {
      setError(e.message || "Upload failed.");
      setPhase("error");
    }
  };

  const restart = () => {
    setItems([]);
    setJob(null);
    setPhase("edit");
    setValues({ ...defaults(tool.options), ...preset });
    setExtras({});
  };

  if (phase === "uploading" || phase === "processing") return <ProcessingView phase={phase} upload={upload} job={job} files={items.length} />;
  if (phase === "done" && job) return <ResultView job={job} tool={tool} onRestart={restart} />;
  if (phase === "error") return <ErrorView message={error} onRetry={() => setPhase("edit")} onRestart={restart} />;

  const header = (compact: boolean) =>
    compact ? (
      <div className="mb-6 flex items-center gap-4">
        <ToolIcon icon={tool.icon} category={tool.category} />
        <div className="min-w-0">
          <h1 className="text-2xl font-extrabold tracking-tight">{seo.h1}</h1>
          <p className="truncate text-sm text-slate-500">{seo.intro}</p>
        </div>
      </div>
    ) : (
      <div className="mx-auto mb-10 max-w-2xl text-center">
        <div className="mb-5 flex justify-center"><ToolIcon icon={tool.icon} category={tool.category} size="lg" /></div>
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">{seo.h1}</h1>
        <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">{seo.intro}</p>
      </div>
    );

  const noticeBar = notice && (
    <div className="mb-4 flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-2.5 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-200" role="status">
      <span className="flex-1">{notice}</span>
      <button onClick={() => setNotice("")} aria-label="Dismiss"><X className="h-4 w-4" /></button>
    </div>
  );

  const cta = (
    <button className="btn-primary w-full py-4 text-base" disabled={!!blocking} onClick={run} title={blocking}>
      {tool.cta} {tool.ui === "convert" && values.format ? `to ${String(values.format).toUpperCase()}` : ""} <ArrowRight className="h-5 w-5" />
    </button>
  );

  const extraPickers = tool.extra_files
    .filter(() => tool.ui !== "sign" && (tool.id !== "add-watermark" || values.kind === "image"))
    .map((ex) => (
      <div key={ex.id}>
        <div className="label">{ex.label}</div>
        <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-slate-300 p-3 text-sm hover:border-brand-400 dark:border-slate-700">
          <ImagePlus className="h-5 w-5 text-slate-400" />
          <span className="flex-1 truncate">{extras[ex.id]?.name || "Choose image…"}</span>
          <input type="file" hidden accept={ex.accept.map((a) => `.${a}`).join(",")} onChange={(e) => setExtras((x) => ({ ...x, [ex.id]: e.target.files?.[0] || null }))} />
        </label>
      </div>
    ));

  const acceptLabel = accept.includes("*")
    ? "Any document, image, audio, video or data file"
    : accept.slice(0, 10).map((a) => a.toUpperCase()).join(", ") + (accept.length > 10 ? "…" : "");

  if (tool.ui === "url") {
    return (
      <div className="py-12">
        {header(false)}
        <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-4">
            <div className="card p-6">
              <label className="label" htmlFor="url">Web page address</label>
              <div className="relative">
                <Globe className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input id="url" className="input py-3 pl-9" placeholder="https://example.com" value={values.url || ""} onChange={(e) => setValues({ ...values, url: e.target.value })} onKeyDown={(e) => e.key === "Enter" && run()} />
              </div>
            </div>
            <div className="text-center text-xs font-semibold uppercase tracking-wider text-slate-400">or</div>
            {items.length ? (
              <FileGrid items={items} setItems={setItems} sortable={false} accept={accept} multiple={false} onAdd={addFiles} />
            ) : (
              <Dropzone compact accept={accept} multiple={false} onFiles={addFiles} title="Upload an HTML file" subtitle=".html or .htm" />
            )}
          </div>
          <aside className="card h-fit space-y-5 p-5">
            <OptionsForm options={tool.options} values={values} setValues={setValues} hide={["url"]} />
            {cta}
          </aside>
        </div>
        <SeoSection seo={seo} />
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="py-12 sm:py-16">
        {header(false)}
        <div className="mx-auto max-w-3xl">
          {noticeBar}
          <Dropzone accept={accept} multiple={tool.multiple} onFiles={addFiles} subtitle={`or drop ${tool.multiple ? "files" : "a file"} here · ${acceptLabel}`} />
          <TrustRow ttl={ttl} />
          {tool.id === "studio" && (
            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              {[["1", "Drop anything", "PDF, Word, PowerPoint, Excel, images, e-mails, e-books…"], ["2", "Arrange & add steps", "Reorder, compress, OCR, watermark, number pages, protect."], ["3", "Export any format", "One PDF, a PowerPoint deck, a Word file, images and more."]].map(([n, t, d]) => (
                <div key={n} className="card p-5">
                  <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white">{n}</div>
                  <div className="font-semibold">{t}</div>
                  <div className="mt-1 text-sm text-slate-500">{d}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <SeoSection seo={seo} />
      </div>
    );
  }

  if (tool.ui === "sign") {
    return (
      <div className="py-8">
        <BackLink />
        {header(true)}
        <SignEditor file={items[0].file} onSignature={onSignature} onPlacement={onPlacement} />
        <div className="sticky bottom-4 mx-auto mt-6 max-w-md">{cta}</div>
      </div>
    );
  }

  const sortable = tool.multiple && ["merge-pdf", "studio", "jpg-to-pdf", "convert", "any-to-pdf", "compare-pdf", "word-to-pdf", "excel-to-pdf", "powerpoint-to-pdf"].includes(tool.id);
  return (
    <div className="py-8">
      <BackLink />
      {header(true)}
      {noticeBar}
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <section>
          {tool.ui === "organize" ? (
            <OrganizeEditor file={items[0].file} onChange={onLayout} />
          ) : (
            <>
              {sortable && items.length > 1 && (
                <p className="mb-3 flex items-center gap-1.5 text-sm text-slate-500"><Sparkles className="h-4 w-4 text-brand-500" /> Drag files to set the order.</p>
              )}
              <FileGrid items={items} setItems={setItems} sortable={sortable} accept={accept} multiple={tool.multiple} onAdd={addFiles} />
            </>
          )}
        </section>
        <aside className="h-fit lg:sticky lg:top-20">
          <div className="card space-y-5 p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-bold">{tool.ui === "studio" ? "Workflow" : tool.ui === "convert" ? "Convert to" : "Options"}</h2>
              <span className="text-xs text-slate-500">{items.length} file{items.length === 1 ? "" : "s"}</span>
            </div>
            {tool.ui === "studio" ? (
              <StudioPanel values={values} setValues={setValues} />
            ) : tool.ui === "convert" ? (
              <>
                <FormatPicker catalog={catalog} names={items.map((i) => i.file.name)} value={values.format} onChange={(v) => setValues({ ...values, format: v })} />
                <OptionsForm options={tool.options} values={values} setValues={setValues} hide={["format"]} />
              </>
            ) : tool.options.filter((o) => o.id !== "layout").length ? (
              <OptionsForm options={tool.options} values={values} setValues={setValues} hide={["layout"]} />
            ) : (
              <p className="text-sm text-slate-500">No options needed — just click the button.</p>
            )}
            {extraPickers}
            {cta}
            {blocking && <p className="-mt-2 text-center text-xs text-slate-500">{blocking}</p>}
          </div>
        </aside>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-700">
      <ChevronLeft className="h-4 w-4" /> All tools
    </Link>
  );
}
