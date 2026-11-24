import { useEffect, useState } from "react";
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSortingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { FilePlus, Loader2, RotateCcw, RotateCw, Trash2, Undo2 } from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { loadPdf, renderPage } from "../pdf";

export type PageItem = { key: string; p: number; r: number };

function Thumb({ doc, item }: { doc: PDFDocumentProxy; item: PageItem }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (item.p < 0) return;
    let alive = true;
    renderPage(doc, item.p, 150, item.r).then((u) => alive && setUrl(u));
    return () => {
      alive = false;
    };
  }, [doc, item.p, item.r]);
  if (item.p < 0) return <div className="flex aspect-[1/1.414] w-full items-center justify-center bg-white text-xs text-slate-400 ring-1 ring-slate-200">Blank page</div>;
  return url ? (
    <img src={url} alt={`Page ${item.p + 1}`} className="max-h-full max-w-full shadow ring-1 ring-slate-200" draggable={false} />
  ) : (
    <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
  );
}

function PageCard({ doc, item, index, onRotate, onDelete, onBlank }: { doc: PDFDocumentProxy; item: PageItem; index: number; onRotate: (d: number) => void; onDelete: () => void; onBlank: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.key });
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`group card relative p-2 ${isDragging ? "z-10 shadow-2xl ring-2 ring-brand-500" : ""}`}>
      <div {...attributes} {...listeners} className="flex h-40 cursor-grab items-center justify-center overflow-hidden rounded-lg bg-slate-100 p-2 active:cursor-grabbing dark:bg-slate-800">
        <Thumb doc={doc} item={item} />
      </div>
      <div className="mt-1.5 text-center text-xs font-semibold text-slate-500">{index + 1}</div>
      <div className="absolute inset-x-0 top-3 flex justify-center gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
        {[
          { icon: RotateCcw, label: "Rotate left", fn: () => onRotate(-90) },
          { icon: RotateCw, label: "Rotate right", fn: () => onRotate(90) },
          { icon: FilePlus, label: "Insert blank page after", fn: onBlank },
          { icon: Trash2, label: "Delete page", fn: onDelete },
        ].map(({ icon: Icon, label, fn }) => (
          <button key={label} onClick={fn} title={label} aria-label={label} className="rounded-lg bg-white/95 p-1.5 text-slate-700 shadow hover:bg-brand-600 hover:text-white dark:bg-slate-800 dark:text-slate-200">
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>
    </div>
  );
}

let k = 0;

export function OrganizeEditor({ file, onChange }: { file: File; onChange: (layout: PageItem[]) => void }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PageItem[]>([]);
  const [initial, setInitial] = useState<PageItem[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  useEffect(() => {
    setErr(null);
    loadPdf(file)
      .then((d) => {
        setDoc(d);
        const init = Array.from({ length: d.numPages }, (_, i) => ({ key: `p${++k}`, p: i, r: 0 }));
        setPages(init);
        setInitial(init);
      })
      .catch(() => setErr("This PDF can't be previewed (it may be encrypted or damaged). Unlock or repair it first."));
  }, [file]);

  useEffect(() => {
    onChange(pages);
  }, [pages, onChange]);

  const update = (fn: (p: PageItem[]) => PageItem[]) => setPages((cur) => fn(cur));
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    update((cur) => arrayMove(cur, cur.findIndex((x) => x.key === e.active.id), cur.findIndex((x) => x.key === e.over!.id)));
  };

  if (err) return <div className="card p-6 text-sm text-red-600">{err}</div>;
  if (!doc) return <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-brand-600" /></div>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-500">{pages.length} page(s) · drag to reorder, hover a page for actions</span>
        <div className="ml-auto flex gap-2">
          <button className="btn-outline px-3 py-1.5 text-xs" onClick={() => update((c) => c.map((x) => ({ ...x, r: (x.r + 90) % 360 })))}>
            <RotateCw className="h-3.5 w-3.5" /> Rotate all
          </button>
          <button className="btn-outline px-3 py-1.5 text-xs" onClick={() => update((c) => [...c].reverse())}>Reverse order</button>
          <button className="btn-outline px-3 py-1.5 text-xs" onClick={() => setPages(initial)}>
            <Undo2 className="h-3.5 w-3.5" /> Reset
          </button>
        </div>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={pages.map((p) => p.key)} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {pages.map((it, i) => (
              <PageCard
                key={it.key}
                doc={doc}
                item={it}
                index={i}
                onRotate={(d) => update((c) => c.map((x) => (x.key === it.key ? { ...x, r: (x.r + d + 360) % 360 } : x)))}
                onDelete={() => update((c) => c.filter((x) => x.key !== it.key))}
                onBlank={() => update((c) => { const n = [...c]; n.splice(i + 1, 0, { key: `p${++k}`, p: -1, r: 0 }); return n; })}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
