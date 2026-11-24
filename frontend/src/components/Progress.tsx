import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock, Download, ExternalLink, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { deleteJob, downloadUrl, extOf, formatBytes, type JobState, type Tool } from "../api";
import { ToolIcon } from "../icons";
import { useApp } from "../store";

export function ProcessingView({ phase, upload, job, files }: { phase: "uploading" | "processing"; upload: number; job: JobState | null; files: number }) {
  const pct = phase === "uploading" ? upload * 100 : (job?.progress || 0) * 100;
  const label = phase === "uploading" ? `Uploading ${files} file${files === 1 ? "" : "s"}…` : job?.stage || "Processing…";
  return (
    <div className="mx-auto max-w-xl py-24 text-center">
      <div className="mx-auto mb-8 flex h-20 w-20 items-center justify-center rounded-3xl bg-brand-100 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
        <Loader2 className="h-10 w-10 animate-spin" />
      </div>
      <h2 className="text-2xl font-bold">{phase === "uploading" ? "Uploading" : "Working on it"}</h2>
      <p className="mt-2 text-slate-500" aria-live="polite">{label}</p>
      <div className="mt-8 h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
        {phase === "processing" && pct < 3 ? (
          <div className="animate-indeterminate h-full w-1/3 rounded-full bg-brand-600" />
        ) : (
          <div className="h-full rounded-full bg-linear-to-r from-brand-500 to-violet-500 transition-all duration-500" style={{ width: `${Math.max(3, pct)}%` }} />
        )}
      </div>
      <p className="mt-3 text-sm font-semibold text-slate-600 dark:text-slate-400">{Math.round(pct)}%</p>
    </div>
  );
}

const NEXT_TOOLS = ["compress-pdf", "merge-pdf", "split-pdf", "organize-pdf", "sign-pdf", "add-watermark", "page-numbers", "protect-pdf", "pdf-to-word", "ocr-pdf", "convert"];

export function ResultView({ job, tool, onRestart }: { job: JobState; tool: Tool; onRestart: () => void }) {
  const { catalog, handoff } = useApp();
  const nav = useNavigate();
  const [left, setLeft] = useState(job.expires_in);
  const [deleted, setDeleted] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const result = job.result!;
  const ext = extOf(result.name);

  useEffect(() => {
    const t = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  const continueWith = async (id: string) => {
    setBusy(id);
    try {
      const blob = await (await fetch(downloadUrl(job.id))).blob();
      handoff([new File([blob], result.name, { type: blob.type })]);
      nav(`/${id}`);
    } finally {
      setBusy(null);
    }
  };

  const shrink = tool.id === "compress-pdf" && job.input_bytes > 0 && result.size < job.input_bytes;
  const next = ext === "pdf" && catalog ? NEXT_TOOLS.filter((id) => id !== tool.id).map((id) => catalog.tools.find((t) => t.id === id)!).filter(Boolean) : [];

  return (
    <div className="mx-auto max-w-3xl py-16 text-center">
      <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
        <CheckCircle2 className="h-10 w-10" />
      </div>
      <h2 className="text-3xl font-extrabold tracking-tight">Your file is ready</h2>
      {job.message && <p className="mx-auto mt-3 max-w-xl text-slate-600 dark:text-slate-300">{job.message}</p>}

      {shrink && (
        <div className="mx-auto mt-6 flex max-w-md items-center justify-center gap-4 rounded-2xl bg-emerald-50 p-4 dark:bg-emerald-500/10">
          <div className="text-sm text-slate-500 line-through">{formatBytes(job.input_bytes)}</div>
          <ArrowRight className="h-4 w-4 text-emerald-600" />
          <div className="text-lg font-bold text-emerald-700 dark:text-emerald-300">{formatBytes(result.size)}</div>
          <div className="rounded-full bg-emerald-600 px-2.5 py-0.5 text-xs font-bold text-white">−{Math.round(100 - (result.size * 100) / job.input_bytes)}%</div>
        </div>
      )}

      {!deleted && ["jpg", "jpeg", "png", "webp", "gif", "svg", "avif", "bmp"].includes(ext) && (
        <div className="checker mx-auto mt-8 flex max-h-80 max-w-md items-center justify-center overflow-hidden rounded-2xl border border-slate-200 p-3 dark:border-slate-700">
          <img src={`${downloadUrl(job.id)}?inline=true`} alt="Result preview" className="max-h-72 object-contain" />
        </div>
      )}
      {!deleted && ["mp4", "webm", "mov"].includes(ext) && (
        <video src={`${downloadUrl(job.id)}?inline=true`} controls className="mx-auto mt-8 max-h-80 rounded-2xl bg-black" />
      )}
      {!deleted && ["mp3", "wav", "ogg", "opus", "m4a", "flac"].includes(ext) && (
        <audio src={`${downloadUrl(job.id)}?inline=true`} controls className="mx-auto mt-8 w-full max-w-md" />
      )}

      {deleted ? (
        <p className="mt-8 font-medium text-emerald-700 dark:text-emerald-300">Your files have been permanently deleted from our servers.</p>
      ) : (
        <>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a href={downloadUrl(job.id)} className="btn-primary px-8 py-4 text-base" download>
              <Download className="h-5 w-5" /> Download {ext.toUpperCase()}
            </a>
            {ext === "pdf" && (
              <a href={`${downloadUrl(job.id)}?inline=true`} target="_blank" rel="noreferrer" className="btn-outline px-5 py-4">
                <ExternalLink className="h-4 w-4" /> Preview
              </a>
            )}
          </div>
          <p className="mt-3 text-sm text-slate-500">
            {result.name} · {formatBytes(result.size)}
            {job.seconds ? ` · done in ${job.seconds}s` : ""}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2 text-sm text-slate-500">
            <Clock className="h-4 w-4" /> Auto-deleted in {Math.floor(left / 60)} min
            <button
              className="btn-ghost px-2 py-1 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
              onClick={async () => {
                await deleteJob(job.id);
                setDeleted(true);
              }}
            >
              <Trash2 className="h-4 w-4" /> Delete now
            </button>
          </div>
        </>
      )}

      <div className="mt-10">
        <button className="btn-outline" onClick={onRestart}>
          <RotateCcw className="h-4 w-4" /> Start over
        </button>
      </div>

      {next.length > 0 && !deleted && (
        <div className="mt-14 text-left">
          <h3 className="mb-4 text-center text-sm font-semibold uppercase tracking-wider text-slate-500">Continue with</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {next.slice(0, 9).map((t) => (
              <button key={t.id} disabled={!!busy} onClick={() => continueWith(t.id)} className="card flex items-center gap-3 p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md">
                <ToolIcon icon={t.icon} category={t.category} size="sm" />
                <span className="flex-1 text-sm font-semibold">{t.name}</span>
                {busy === t.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4 text-slate-400" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ErrorView({ message, onRetry, onRestart }: { message: string; onRetry: () => void; onRestart: () => void }) {
  return (
    <div className="mx-auto max-w-xl py-24 text-center">
      <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-red-100 text-red-600 dark:bg-red-500/15 dark:text-red-300">
        <AlertTriangle className="h-10 w-10" />
      </div>
      <h2 className="text-2xl font-bold">We couldn't finish that</h2>
      <p className="mt-3 text-slate-600 dark:text-slate-300">{message}</p>
      <div className="mt-8 flex justify-center gap-3">
        <button className="btn-primary" onClick={onRetry}>Back to options</button>
        <button className="btn-outline" onClick={onRestart}>Start over</button>
      </div>
    </div>
  );
}
