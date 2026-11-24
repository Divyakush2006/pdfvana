import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, BadgeCheck, Clock, FileStack, Infinity as InfinityIcon, Lock, Search, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { setHead, type Tool } from "../api";
import { ToolIcon } from "../icons";
import { useApp } from "../store";

function ToolCard({ t }: { t: Tool }) {
  return (
    <Link
      to={`/${t.id}`}
      className="group card relative flex flex-col gap-3 p-5 transition duration-200 hover:-translate-y-1 hover:border-brand-300 hover:shadow-lg hover:shadow-brand-600/5 dark:hover:border-brand-500/50"
    >
      <div className="flex items-start justify-between">
        <ToolIcon icon={t.icon} category={t.category} />
        {t.badge && <span className="rounded-full bg-linear-to-r from-brand-600 to-violet-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">{t.badge}</span>}
      </div>
      <div>
        <h3 className="font-bold tracking-tight group-hover:text-brand-700 dark:group-hover:text-brand-300">{t.name}</h3>
        <p className="mt-1 line-clamp-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{t.description}</p>
      </div>
    </Link>
  );
}

function QuickConvert() {
  const { catalog } = useApp();
  const nav = useNavigate();
  const sources = useMemo(() => [...new Set(catalog?.pairs.map((p) => p.from) || [])], [catalog]);
  const [from, setFrom] = useState("jpg");
  const targets = catalog?.pairs.filter((p) => p.from === from).map((p) => p.to) || [];
  const [to, setTo] = useState("png");
  useEffect(() => {
    if (targets.length && !targets.includes(to)) setTo(targets[0]);
  }, [from, targets, to]);
  if (!catalog) return null;
  return (
    <form
      className="mx-auto mt-5 flex max-w-xl flex-wrap items-center justify-center gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        nav(`/${from}-to-${to}`);
      }}
    >
      <span className="text-slate-500">Convert</span>
      <select aria-label="From format" className="input w-auto py-1.5 font-semibold" value={from} onChange={(e) => setFrom(e.target.value)}>
        {sources.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
      </select>
      <span className="text-slate-500">to</span>
      <select aria-label="To format" className="input w-auto py-1.5 font-semibold" value={to} onChange={(e) => setTo(e.target.value)}>
        {targets.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
      </select>
      <button className="btn-primary py-1.5">Go <ArrowRight className="h-4 w-4" /></button>
    </form>
  );
}

export default function Home() {
  const { catalog, error } = useApp();
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [cat, setCat] = useState("all");
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const brand = catalog?.brand || "PDFVana";
    setHead(`${brand} — Free PDF Tools & Universal File Converter (No Sign-up)`,
      "Merge, split, compress and convert PDF, Word, Excel, PowerPoint, images, audio and video. 100% free, no sign-up, no watermarks, no limits.",
      catalog ? `${catalog.site.replace(/\/$/, "")}/` : undefined);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "")) {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [catalog]);

  const tools = useMemo(() => {
    if (!catalog) return [];
    const needle = q.trim().toLowerCase();
    return catalog.tools.filter(
      (t) => (cat === "all" || t.category === cat) && (!needle || `${t.name} ${t.description} ${t.keywords} ${t.accept.join(" ")}`.toLowerCase().includes(needle)),
    );
  }, [catalog, q, cat]);
  const pairHits = useMemo(() => {
    const needle = q.trim().toLowerCase().replace(/\s+/g, " ");
    if (!catalog || needle.length < 2) return [];
    return catalog.pairs.filter((p) => `${p.from} to ${p.to} ${p.h1}`.toLowerCase().includes(needle)).slice(0, 8);
  }, [catalog, q]);

  return (
    <>
      <section className="hero-glow -mx-4 px-4 pb-10 pt-16 text-center sm:pt-20">
        <div className="mx-auto max-w-3xl">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-300">
            <Sparkles className="h-3.5 w-3.5" /> 100% free · Open source · No sign-up · No watermarks
          </span>
          <h1 className="mt-6 text-4xl font-extrabold tracking-tight sm:text-6xl">
            Every file tool you need,
            <br />
            <span className="bg-linear-to-r from-brand-600 via-violet-600 to-fuchsia-600 bg-clip-text text-transparent">free forever.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600 dark:text-slate-400">
            Merge, split, compress, sign and protect PDFs — and convert anything to anything: Word, PowerPoint, Excel, images, SVG, ICO, audio and
            video. Professional quality, private by design.
          </p>
          <div className="relative mx-auto mt-8 max-w-xl">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <input
              ref={search}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search 49 tools — try “compress”, “heic to jpg” or “sign”"
              className="input rounded-2xl py-4 pl-12 pr-12 text-base shadow-sm"
              aria-label="Search tools"
            />
            <kbd className="absolute right-4 top-1/2 hidden -translate-y-1/2 rounded-md border border-slate-300 px-1.5 text-xs text-slate-400 sm:block dark:border-slate-700">/</kbd>
          </div>
          <QuickConvert />
        </div>
      </section>

      {error && !catalog && <div className="mx-auto mb-6 max-w-xl rounded-xl bg-amber-50 p-4 text-center text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-200">{error}</div>}

      {catalog && (
        <>
          <div className="mb-8 flex gap-2 overflow-x-auto pb-1 sm:flex-wrap sm:justify-center" role="tablist" aria-label="Tool categories">
            {[{ id: "all", name: "All tools" }, ...catalog.categories].map((c) => (
              <button
                key={c.id}
                role="tab"
                aria-selected={cat === c.id}
                onClick={() => setCat(c.id)}
                className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${
                  cat === c.id ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-slate-300 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-800"
                }`}
              >
                {c.name}
              </button>
            ))}
          </div>

          {pairHits.length > 0 && (
            <div className="mb-6 flex flex-wrap justify-center gap-2">
              {pairHits.map((p) => (
                <Link key={p.slug} to={`/${p.slug}`} className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1.5 text-sm font-semibold text-brand-800 hover:bg-brand-100 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-200">
                  {p.h1}
                </Link>
              ))}
            </div>
          )}

          {cat === "all" && !q && (
            <Link to="/studio" className="group mb-6 block overflow-hidden rounded-3xl bg-linear-to-br from-brand-600 via-violet-600 to-fuchsia-600 p-px">
              <div className="flex flex-col gap-6 rounded-[23px] bg-linear-to-br from-brand-600 to-violet-700 p-7 text-white sm:flex-row sm:items-center sm:p-9">
                <div className="flex-1">
                  <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold">
                    <FileStack className="h-3.5 w-3.5" /> Document Studio
                  </div>
                  <h2 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Merge anything. Export to anything.</h2>
                  <p className="mt-2 max-w-2xl text-brand-100">
                    Drop a Word report, a scanned receipt, a spreadsheet and a slide deck — arrange them, add OCR, page numbers, a watermark or
                    compression, then export one PDF, PowerPoint, Word file or set of images. Workflows others charge for, free.
                  </p>
                </div>
                <span className="inline-flex items-center gap-2 self-start rounded-xl bg-white px-5 py-3 font-semibold text-brand-800 shadow-lg transition group-hover:gap-3 sm:self-center">
                  Open Studio <ArrowRight className="h-4 w-4" />
                </span>
              </div>
            </Link>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {tools.map((t) => <ToolCard key={t.id} t={t} />)}
          </div>
          {tools.length === 0 && pairHits.length === 0 && (
            <p className="py-16 text-center text-slate-500">No tool matches “{q}”. Try the <Link className="text-brand-700 underline" to="/convert">Universal Converter</Link>.</p>
          )}

          <section className="mt-20">
            <h2 className="text-center text-2xl font-extrabold tracking-tight">Popular conversions</h2>
            <div className="mx-auto mt-6 flex max-w-5xl flex-wrap justify-center gap-2">
              {catalog.pairs.map((p) => (
                <Link key={p.slug} to={`/${p.slug}`} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:border-brand-400 hover:text-brand-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                  {p.from.toUpperCase()} → {p.to.toUpperCase()}
                </Link>
              ))}
            </div>
          </section>
        </>
      )}

      {!catalog && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-busy="true">
          {Array.from({ length: 12 }).map((_, i) => <div key={i} className="card h-40 animate-pulse" />)}
        </div>
      )}

      <section className="mt-24">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">Built like enterprise software. Free like a public utility.</h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-slate-600 dark:text-slate-400">
          Industrial-grade document, image and media engines behind one fast, simple interface — on the web or on your own servers.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            [InfinityIcon, "Free, with no catch", "No daily task limits, no file-count caps, no watermarks, no premium tier. Every feature for everyone."],
            [ShieldCheck, "Private by design", "No account and no trackers. Files are processed in isolation and permanently deleted after an hour — or instantly."],
            [Zap, "Fast and accurate", "Warm conversion engines and parallel processing. Office files convert with the fidelity of a real office suite."],
            [FileStack, "Works with any file", "PDF, Office, iWork, ODF, HEIC, SVG, ICO, EPUB, Markdown, HTML, e-mail, CSV, JSON, MP4, MOV, MP3, WAV and more."],
            [BadgeCheck, "Standards compliant", "AES-256 encryption, true redaction, PDF/A archiving and searchable OCR in 28 languages including Indian scripts."],
            [Lock, "Open & self-hostable", "Apache-2.0 licensed and runs anywhere with Docker. Keep everything inside your own network if your policies require it."],
          ].map(([Icon, title, text]: any) => (
            <div key={title} className="card p-6">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300"><Icon className="h-5 w-5" /></span>
              <h3 className="mt-4 font-bold">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-8 flex items-center justify-center gap-2 text-sm text-slate-500"><Clock className="h-4 w-4" /> Files auto-delete after {Math.round((catalog?.limits.ttl_seconds || 3600) / 60)} minutes.</p>
      </section>
    </>
  );
}
