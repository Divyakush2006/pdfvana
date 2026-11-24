import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { PDFDocumentProxy } from "pdfjs-dist";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const docs = new WeakMap<File, Promise<PDFDocumentProxy>>();

export function isPdf(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

export function loadPdf(file: File): Promise<PDFDocumentProxy> {
  let p = docs.get(file);
  if (!p) {
    p = file.arrayBuffer().then((buf) => pdfjs.getDocument({ data: buf }).promise);
    docs.set(file, p);
  }
  return p;
}

// Render queue so dozens of thumbnails don't freeze the page.
let active = 0;
const waiting: (() => void)[] = [];
async function slot<T>(fn: () => Promise<T>): Promise<T> {
  if (active >= 3) await new Promise<void>((r) => waiting.push(r));
  active++;
  try {
    return await fn();
  } finally {
    active--;
    waiting.shift()?.();
  }
}

export function renderPage(doc: PDFDocumentProxy, index: number, width: number, rotation = 0): Promise<string> {
  return slot(async () => {
    const page = await doc.getPage(index + 1);
    const base = page.getViewport({ scale: 1, rotation: (page.rotate + rotation) % 360 });
    const scale = (width * (window.devicePixelRatio || 1)) / base.width;
    const vp = page.getViewport({ scale, rotation: (page.rotate + rotation) % 360 });
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(vp.width);
    canvas.height = Math.ceil(vp.height);
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({ canvas, canvasContext: ctx, viewport: vp }).promise;
    const url = canvas.toDataURL("image/jpeg", 0.82);
    canvas.width = canvas.height = 0;
    return url;
  });
}

export async function pageSize(doc: PDFDocumentProxy, index: number) {
  const page = await doc.getPage(index + 1);
  const vp = page.getViewport({ scale: 1 });
  return { width: vp.width, height: vp.height };
}
