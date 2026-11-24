import { Link, NavLink, useLocation } from "react-router-dom";
import { ChevronDown, Menu, Moon, ShieldCheck, Sun, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { GithubMark, Logo, ToolIcon } from "../icons";
import { useApp, useTheme } from "../store";

const QUICK: [string, string][] = [
  ["merge-pdf", "Merge"], ["compress-pdf", "Compress"], ["convert", "Convert"], ["image-converter", "Images"],
  ["video-converter", "Video"], ["studio", "Studio"],
];

export function Header() {
  const { catalog } = useApp();
  const { dark, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const loc = useLocation();
  const ref = useRef<HTMLDivElement>(null);
  const brand = catalog?.brand || "PDFVana";

  useEffect(() => {
    setOpen(false);
    setMobile(false);
  }, [loc.pathname]);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, []);

  const nav = QUICK.map(([id, label]) => (
    <NavLink key={id} to={`/${id}`} className={({ isActive }) => `btn-ghost px-3 py-2 ${isActive ? "text-brand-700 dark:text-brand-400" : ""}`}>
      {label}
    </NavLink>
  ));

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/85 backdrop-blur-md dark:border-slate-800 dark:bg-slate-950/85">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-2 px-4">
        <Link to="/" className="mr-3" aria-label={`${brand} home`}>
          <Logo brand={brand} />
        </Link>
        <nav className="hidden items-center gap-0.5 lg:flex" aria-label="Main">
          {nav}
          <div className="relative" ref={ref}>
            <button className="btn-ghost px-3 py-2" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="true">
              All tools <ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} />
            </button>
            {open && catalog && (
              <div className="card absolute left-1/2 top-12 z-50 grid max-h-[78vh] w-[1100px] max-w-[96vw] -translate-x-1/2 grid-cols-5 gap-x-5 gap-y-5 overflow-y-auto p-6 shadow-2xl">
                {catalog.categories.map((c) => (
                  <div key={c.id}>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{c.name}</div>
                    <ul className="space-y-0.5">
                      {catalog.tools
                        .filter((t) => t.category === c.id)
                        .map((t) => (
                          <li key={t.id}>
                            <Link to={`/${t.id}`} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                              <ToolIcon icon={t.icon} category={t.category} size="sm" />
                              <span className="leading-tight">{t.name}</span>
                            </Link>
                          </li>
                        ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <Link to="/privacy" className="btn-ghost hidden px-3 py-2 sm:inline-flex">
            <ShieldCheck className="h-4 w-4 text-emerald-600" /> Privacy
          </Link>
          {catalog?.repo && (
            <a href={catalog.repo} target="_blank" rel="noreferrer" className="btn-ghost hidden p-2.5 sm:inline-flex" aria-label="Source code on GitHub">
              <GithubMark />
            </a>
          )}
          <button className="btn-ghost p-2.5" onClick={toggle} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <button className="btn-ghost p-2.5 lg:hidden" onClick={() => setMobile((v) => !v)} aria-label="Menu" aria-expanded={mobile}>
            {mobile ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {mobile && (
        <div className="max-h-[75vh] overflow-y-auto border-t border-slate-200 px-4 py-3 lg:hidden dark:border-slate-800">
          <div className="grid grid-cols-2 gap-1">{nav}</div>
          {catalog?.categories.map((c) => (
            <div key={c.id} className="mt-3">
              <div className="px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">{c.name}</div>
              <div className="grid grid-cols-2">
                {catalog.tools.filter((t) => t.category === c.id).map((t) => (
                  <Link key={t.id} to={`/${t.id}`} className="rounded-lg px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">{t.name}</Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </header>
  );
}

const FOOTER: [string, string[]][] = [
  ["PDF", ["merge-pdf", "compress-pdf", "split-pdf", "pdf-to-word", "sign-pdf", "protect-pdf"]],
  ["Convert", ["convert", "word-to-pdf", "pdf-to-powerpoint", "pdf-to-excel", "jpg-to-pdf", "html-to-pdf"]],
  ["Images", ["image-converter", "compress-image", "resize-image", "image-to-svg", "favicon-generator", "html-to-image"]],
  ["Audio & video", ["video-converter", "audio-converter", "video-to-gif", "compress-video", "data-converter", "studio"]],
];

export function Footer() {
  const { catalog } = useApp();
  const brand = catalog?.brand || "PDFVana";
  const pairs = catalog?.pairs.slice(0, 24) || [];
  return (
    <footer className="mt-24 border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:grid-cols-2 lg:grid-cols-6">
        <div className="lg:col-span-2">
          <Logo brand={brand} />
          <p className="mt-3 max-w-sm text-sm text-slate-600 dark:text-slate-400">
            Professional PDF, document, image and media tools — free for everyone. No sign-up, no watermarks, no limits, and your files
            are deleted automatically.
          </p>
          <p className="mt-2 max-w-sm text-xs italic text-slate-500">Vana (वन) is Sanskrit for “forest” — a forest of free tools for every file.</p>
          {catalog?.repo && (
            <a href={catalog.repo} className="btn-outline mt-4 px-3 py-2" target="_blank" rel="noreferrer">
              <GithubMark /> Star us on GitHub
            </a>
          )}
        </div>
        {catalog &&
          FOOTER.map(([title, ids]) => (
            <div key={title}>
              <div className="mb-3 text-sm font-semibold">{title}</div>
              <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
                {ids.map((id) => {
                  const t = catalog.tools.find((x) => x.id === id);
                  return t ? (
                    <li key={id}>
                      <Link to={`/${id}`} className="hover:text-brand-700">{t.name}</Link>
                    </li>
                  ) : null;
                })}
              </ul>
            </div>
          ))}
      </div>
      {pairs.length > 0 && (
        <div className="mx-auto max-w-7xl px-4 pb-10">
          <div className="mb-3 text-sm font-semibold">Popular conversions</div>
          <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-500">
            {pairs.map((p) => (
              <Link key={p.slug} to={`/${p.slug}`} className="hover:text-brand-700">{p.h1.replace(" Converter", "")}</Link>
            ))}
          </div>
        </div>
      )}
      <div className="border-t border-slate-200 py-5 text-center text-xs text-slate-500 dark:border-slate-800">
        © {new Date().getFullYear()} {brand} · Free & open source (Apache-2.0) · <Link to="/privacy" className="hover:underline">Privacy & security</Link> ·{" "}
        <a href="/api/docs" className="hover:underline">Developer API</a>
        {catalog?.version ? ` · v${catalog.version}` : ""}
      </div>
    </footer>
  );
}

export function Page({ children }: { children: ReactNode }) {
  return <main className="mx-auto max-w-7xl px-4">{children}</main>;
}
