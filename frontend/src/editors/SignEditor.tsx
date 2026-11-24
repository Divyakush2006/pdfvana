import { useCallback, useEffect, useRef, useState } from "react";
import "@fontsource/dancing-script/600.css";
import "@fontsource/great-vibes/400.css";
import "@fontsource/caveat/600.css";
import { ChevronLeft, ChevronRight, Eraser, ImageUp, Loader2, PenLine, Type } from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { loadPdf, renderPage } from "../pdf";

export type Placement = { x: number; y: number; width: number; pages: string };

const INKS = ["#0f172a", "#1d4ed8", "#b91c1c"];
const FONTS = [
  { name: "Dancing Script", css: "600 64px 'Dancing Script'" },
  { name: "Great Vibes", css: "64px 'Great Vibes'" },
  { name: "Caveat", css: "600 64px 'Caveat'" },
];

function trim(canvas: HTMLCanvasElement): HTMLCanvasElement {
  const ctx = canvas.getContext("2d")!;
  const { width, height } = canvas;
  const data = ctx.getImageData(0, 0, width, height).data;
  let x0 = width, y0 = height, x1 = -1, y1 = -1;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++)
      if (data[(y * width + x) * 4 + 3] > 8) {
        if (x < x0) x0 = x;
        if (y < y0) y0 = y;
        if (x > x1) x1 = x;
        if (y > y1) y1 = y;
      }
  if (x1 < 0) return canvas;
  const pad = 6;
  const out = document.createElement("canvas");
  out.width = x1 - x0 + 1 + pad * 2;
  out.height = y1 - y0 + 1 + pad * 2;
  out.getContext("2d")!.drawImage(canvas, x0 - pad, y0 - pad, out.width, out.height, 0, 0, out.width, out.height);
  return out;
}

const toFile = (c: HTMLCanvasElement) =>
  new Promise<File>((res) => c.toBlob((b) => res(new File([b!], "signature.png", { type: "image/png" })), "image/png"));

function DrawPad({ ink, onDone }: { ink: string; onDone: (f: File | null) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const dirty = useRef(false);

  useEffect(() => {
    const c = ref.current!;
    c.width = c.offsetWidth * 2;
    c.height = c.offsetHeight * 2;
  }, []);

  const pos = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return { x: (e.clientX - r.left) * 2, y: (e.clientY - r.top) * 2 };
  };
  const commit = useCallback(async () => {
    if (!dirty.current) return onDone(null);
    onDone(await toFile(trim(ref.current!)));
  }, [onDone]);

  return (
    <div>
      <canvas
        ref={ref}
        className="checker h-44 w-full touch-none rounded-xl border border-slate-300 dark:border-slate-700"
        onPointerDown={(e) => {
          (e.target as HTMLElement).setPointerCapture(e.pointerId);
          drawing.current = true;
          last.current = pos(e);
        }}
        onPointerMove={(e) => {
          if (!drawing.current) return;
          const ctx = ref.current!.getContext("2d")!;
          const p = pos(e);
          ctx.strokeStyle = ink;
          ctx.lineWidth = 5 * (0.6 + (e.pressure || 0.5) * 0.8);
          ctx.lineCap = ctx.lineJoin = "round";
          ctx.beginPath();
          ctx.moveTo(last.current!.x, last.current!.y);
          ctx.lineTo(p.x, p.y);
          ctx.stroke();
          last.current = p;
          dirty.current = true;
        }}
        onPointerUp={() => {
          drawing.current = false;
          commit();
        }}
      />
      <button
        className="btn-ghost mt-2 px-2 py-1 text-xs"
        onClick={() => {
          const c = ref.current!;
          c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
          dirty.current = false;
          onDone(null);
        }}
      >
        <Eraser className="h-3.5 w-3.5" /> Clear
      </button>
    </div>
  );
}

function TypePad({ ink, onDone }: { ink: string; onDone: (f: File | null) => void }) {
  const [text, setText] = useState("");
  const [font, setFont] = useState(0);
  useEffect(() => {
    const t = setTimeout(async () => {
      if (!text.trim()) return onDone(null);
      await document.fonts.load(FONTS[font].css);
      const c = document.createElement("canvas");
      const ctx = c.getContext("2d")!;
      ctx.font = FONTS[font].css;
      c.width = Math.ceil(ctx.measureText(text).width) + 40;
      c.height = 120;
      ctx.font = FONTS[font].css;
      ctx.fillStyle = ink;
      ctx.textBaseline = "middle";
      ctx.fillText(text, 20, 64);
      onDone(await toFile(trim(c)));
    }, 250);
    return () => clearTimeout(t);
  }, [text, font, ink, onDone]);
  return (
    <div className="space-y-3">
      <input className="input" placeholder="Type your full name" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="grid gap-2">
        {FONTS.map((f, i) => (
          <button key={f.name} onClick={() => setFont(i)} className={`rounded-xl border px-4 py-2 text-left text-3xl ${font === i ? "border-brand-500 ring-1 ring-brand-500" : "border-slate-200 dark:border-slate-700"}`} style={{ fontFamily: `'${f.name}'`, color: ink }}>
            {text || "Your Name"}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SignEditor({ file, onSignature, onPlacement }: { file: File; onSignature: (f: File | null) => void; onPlacement: (p: Placement) => void }) {
  const [tab, setTab] = useState<"draw" | "type" | "upload">("draw");
  const [ink, setInk] = useState(INKS[0]);
  const [sig, setSig] = useState<File | null>(null);
  const [sigUrl, setSigUrl] = useState<string | null>(null);
  const [ratio, setRatio] = useState(0.35);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pageIdx, setPageIdx] = useState(0);
  const [pageUrl, setPageUrl] = useState<string | null>(null);
  const [place, setPlace] = useState({ x: 0.6, y: 0.8, width: 0.28 });
  const [allPages, setAllPages] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<{ mode: "move" | "resize"; sx: number; sy: number; start: typeof place } | null>(null);

  const setSignature = useCallback(
    (f: File | null) => {
      setSig(f);
      onSignature(f);
    },
    [onSignature],
  );

  useEffect(() => {
    loadPdf(file).then((d) => {
      setDoc(d);
      setPageIdx(d.numPages - 1);
    }).catch(() => setDoc(null));
  }, [file]);
  useEffect(() => {
    if (!doc) return;
    setPageUrl(null);
    renderPage(doc, pageIdx, 640).then(setPageUrl);
  }, [doc, pageIdx]);
  useEffect(() => {
    if (!sig) return setSigUrl(null);
    const u = URL.createObjectURL(sig);
    setSigUrl(u);
    const img = new Image();
    img.onload = () => setRatio(img.height / img.width);
    img.src = u;
    return () => URL.revokeObjectURL(u);
  }, [sig]);
  useEffect(() => {
    onPlacement({ ...place, pages: allPages ? "all" : String(pageIdx + 1) });
  }, [place, allPages, pageIdx, onPlacement]);

  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || !stage.current) return;
    const r = stage.current.getBoundingClientRect();
    const dx = (e.clientX - d.sx) / r.width;
    const dy = (e.clientY - d.sy) / r.height;
    if (d.mode === "move") {
      setPlace({ ...d.start, x: Math.min(Math.max(0, d.start.x + dx), 1 - d.start.width), y: Math.min(Math.max(0, d.start.y + dy), 0.98) });
    } else {
      setPlace({ ...d.start, width: Math.min(Math.max(0.05, d.start.width + dx), 1 - d.start.x) });
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="card flex flex-col items-center p-4">
        {doc && (
          <div className="mb-3 flex items-center gap-2 text-sm">
            <button className="btn-ghost p-1.5" disabled={pageIdx === 0} onClick={() => setPageIdx((i) => i - 1)} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
            Page {pageIdx + 1} of {doc.numPages}
            <button className="btn-ghost p-1.5" disabled={pageIdx >= doc.numPages - 1} onClick={() => setPageIdx((i) => i + 1)} aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
          </div>
        )}
        <div ref={stage} className="relative w-full max-w-[640px] select-none bg-slate-100 shadow-lg dark:bg-slate-800" onPointerMove={onPointerMove} onPointerUp={() => (drag.current = null)}>
          {pageUrl ? <img src={pageUrl} alt="Page preview" className="block w-full" draggable={false} /> : <div className="flex aspect-[1/1.414] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
          {sigUrl && pageUrl && (
            <div
              className="absolute cursor-move rounded border-2 border-dashed border-brand-500 bg-brand-500/5"
              style={{ left: `${place.x * 100}%`, top: `${place.y * 100}%`, width: `${place.width * 100}%`, aspectRatio: `${1 / ratio}` }}
              onPointerDown={(e) => {
                (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
                drag.current = { mode: "move", sx: e.clientX, sy: e.clientY, start: place };
              }}
              onPointerMove={onPointerMove}
              onPointerUp={() => (drag.current = null)}
            >
              <img src={sigUrl} alt="Signature" className="h-full w-full object-contain" draggable={false} />
              <span
                className="absolute -bottom-2 -right-2 h-4 w-4 cursor-se-resize rounded-full border-2 border-white bg-brand-600 shadow"
                onPointerDown={(e) => {
                  e.stopPropagation();
                  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
                  drag.current = { mode: "resize", sx: e.clientX, sy: e.clientY, start: place };
                }}
                onPointerMove={onPointerMove}
                onPointerUp={() => (drag.current = null)}
              />
            </div>
          )}
        </div>
        <p className="mt-3 text-xs text-slate-500">{sig ? "Drag the signature to position it; drag the blue dot to resize." : "Create your signature on the right, then place it here."}</p>
      </div>

      <div className="space-y-5">
        <div className="card p-4">
          <div className="mb-4 grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
            {([["draw", PenLine, "Draw"], ["type", Type, "Type"], ["upload", ImageUp, "Upload"]] as const).map(([id, Icon, label]) => (
              <button key={id} onClick={() => { setTab(id); setSignature(null); }} className={`flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium ${tab === id ? "bg-white shadow dark:bg-slate-900" : "text-slate-500"}`}>
                <Icon className="h-4 w-4" /> {label}
              </button>
            ))}
          </div>
          {tab !== "upload" && (
            <div className="mb-3 flex items-center gap-2 text-xs text-slate-500">
              Ink
              {INKS.map((c) => (
                <button key={c} onClick={() => setInk(c)} aria-label={`Ink ${c}`} className={`h-6 w-6 rounded-full ring-offset-2 dark:ring-offset-slate-900 ${ink === c ? "ring-2 ring-brand-500" : ""}`} style={{ background: c }} />
              ))}
            </div>
          )}
          {tab === "draw" && <DrawPad key={ink} ink={ink} onDone={setSignature} />}
          {tab === "type" && <TypePad ink={ink} onDone={setSignature} />}
          {tab === "upload" && (
            <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-slate-300 p-6 text-sm text-slate-500 hover:border-brand-400 dark:border-slate-700">
              <ImageUp className="h-6 w-6" /> Upload a signature or stamp image (PNG with transparency works best)
              <input type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => setSignature(e.target.files?.[0] || null)} />
            </label>
          )}
        </div>
        <label className="card flex cursor-pointer items-center gap-3 p-4 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={allPages} onChange={(e) => setAllPages(e.target.checked)} />
          Place on every page (same position)
        </label>
      </div>
    </div>
  );
}
