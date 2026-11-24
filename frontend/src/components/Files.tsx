import { useEffect, useRef, useState, type ReactNode } from "react";
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { FilePlus2, GripVertical, Loader2, Plus, UploadCloud, X } from "lucide-react";
import { extOf, formatBytes } from "../api";
import { isPdf, loadPdf, renderPage } from "../pdf";

export type FileItem = { id: string; file: File };

let counter = 0;
export const toItems = (files: File[]): FileItem[] => files.map((file) => ({ id: `f${++counter}`, file }));

export function acceptAttr(accept: string[]) {
  return accept.includes("*") ? undefined : accept.map((e) => `.${e}`).join(",");
}

export function filterAccepted(files: File[], accept: string[]) {
  if (accept.includes("*")) return { ok: files, rejected: [] as File[] };
  const ok: File[] = [];
  const rejected: File[] = [];
  files.forEach((f) => (accept.includes(extOf(f.name)) ? ok : rejected).push(f));
  return { ok, rejected };
}

export function Dropzone({
  accept, multiple, onFiles, title, subtitle, compact, children,
}: {
  accept: string[];
  multiple: boolean;
  onFiles: (files: File[]) => void;
  title?: string;
  subtitle?: string;
  compact?: boolean;
  children?: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length) onFiles(multiple ? files : files.slice(0, 1));
      }}
      className={`relative flex flex-col items-center justify-center rounded-3xl border-2 border-dashed text-center transition ${
        compact ? "p-6" : "px-6 py-14 sm:py-20"
      } ${over ? "border-brand-500 bg-brand-50 dark:bg-brand-500/10" : "border-slate-300 bg-white hover:border-brand-400 dark:border-slate-700 dark:bg-slate-900"}`}
    >
      <input
        ref={input}
        type="file"
        hidden
        multiple={multiple}
        accept={acceptAttr(accept)}
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          e.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
      {!compact && (
        <span className="mb-5 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-100 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
          <UploadCloud className="h-8 w-8" />
        </span>
      )}
      <button type="button" className="btn-primary px-8 py-4 text-base" onClick={() => input.current?.click()}>
        <FilePlus2 className="h-5 w-5" /> {title || (multiple ? "Select files" : "Select file")}
      </button>
      <p className="mt-3 text-sm text-slate-500">{subtitle || "or drop them here"}</p>
      {children}
    </div>
  );
}

const thumbCache = new WeakMap<File, Promise<{ url: string | null; pages: number | null }>>();

function thumbnail(file: File) {
  let p = thumbCache.get(file);
  if (!p) {
    p = (async () => {
      if (isPdf(file)) {
        try {
          const doc = await loadPdf(file);
          return { url: await renderPage(doc, 0, 180), pages: doc.numPages };
        } catch {
          return { url: null, pages: null };
        }
      }
      if (/^image\/(png|jpe?g|gif|webp|bmp|svg\+xml|avif)$/.test(file.type)) return { url: URL.createObjectURL(file), pages: null };
      return { url: null, pages: null };
    })();
    thumbCache.set(file, p);
  }
  return p;
}

const EXT_TONE: Record<string, string> = {
  pdf: "bg-red-500", doc: "bg-blue-600", docx: "bg-blue-600", odt: "bg-blue-500", rtf: "bg-blue-500", txt: "bg-slate-500",
  ppt: "bg-orange-600", pptx: "bg-orange-600", odp: "bg-orange-500", key: "bg-orange-500",
  xls: "bg-green-700", xlsx: "bg-green-700", ods: "bg-green-600", csv: "bg-green-600",
  html: "bg-purple-600", htm: "bg-purple-600", md: "bg-slate-700", epub: "bg-teal-600", eml: "bg-sky-600",
  json: "bg-yellow-600", svg: "bg-amber-600", heic: "bg-amber-600", tiff: "bg-amber-600", tif: "bg-amber-600",
  mp4: "bg-fuchsia-600", mov: "bg-fuchsia-600", mkv: "bg-fuchsia-600", webm: "bg-fuchsia-600", avi: "bg-fuchsia-600",
  mp3: "bg-indigo-600", wav: "bg-indigo-600", flac: "bg-indigo-600", m4a: "bg-indigo-600", ogg: "bg-indigo-600",
};

export function FileThumb({ file, className = "" }: { file: File; className?: string }) {
  const [state, setState] = useState<{ url: string | null; pages: number | null } | null>(null);
  useEffect(() => {
    let alive = true;
    thumbnail(file).then((s) => alive && setState(s));
    return () => {
      alive = false;
    };
  }, [file]);
  const ext = extOf(file.name);
  return (
    <div className={`relative flex items-center justify-center overflow-hidden bg-slate-100 dark:bg-slate-800 ${className}`}>
      {state === null ? (
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      ) : state.url ? (
        <img src={state.url} alt="" className="max-h-full max-w-full object-contain shadow-sm" draggable={false} />
      ) : (
        <span className={`rounded-lg px-3 py-4 text-sm font-bold uppercase text-white shadow ${EXT_TONE[ext] || "bg-slate-500"}`}>{ext || "file"}</span>
      )}
      {state?.pages ? (
        <span className="absolute bottom-1.5 right-1.5 rounded-md bg-slate-900/75 px-1.5 py-0.5 text-[10px] font-semibold text-white">
          {state.pages} {state.pages === 1 ? "page" : "pages"}
        </span>
      ) : null}
    </div>
  );
}

function FileCard({ item, index, sortable, onRemove }: { item: FileItem; index: number; sortable: boolean; onRemove: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id, disabled: !sortable });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`group card relative overflow-hidden p-2 ${isDragging ? "z-10 shadow-2xl ring-2 ring-brand-500" : ""}`}
    >
      <div {...attributes} {...listeners} className={sortable ? "cursor-grab active:cursor-grabbing" : ""}>
        <FileThumb file={item.file} className="h-44 rounded-xl" />
      </div>
      <div className="mt-2 flex items-start gap-1.5 px-1">
        {sortable && (
          <span className="mt-0.5 text-xs font-bold text-slate-400" title="Order">
            {index + 1}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium" title={item.file.name}>{item.file.name}</div>
          <div className="text-[11px] text-slate-500">{formatBytes(item.file.size)}</div>
        </div>
        {sortable && <GripVertical className="h-4 w-4 text-slate-300" />}
      </div>
      <button
        onClick={onRemove}
        className="absolute right-3 top-3 rounded-full bg-white/95 p-1.5 text-slate-600 opacity-0 shadow transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 focus:opacity-100 dark:bg-slate-800 dark:text-slate-300"
        aria-label={`Remove ${item.file.name}`}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function FileGrid({
  items, setItems, sortable, accept, multiple, onAdd,
}: {
  items: FileItem[];
  setItems: (items: FileItem[]) => void;
  sortable: boolean;
  accept: string[];
  multiple: boolean;
  onAdd: (files: File[]) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const input = useRef<HTMLInputElement>(null);
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const from = items.findIndex((i) => i.id === e.active.id);
    const to = items.findIndex((i) => i.id === e.over!.id);
    setItems(arrayMove(items, from, to));
  };
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <SortableContext items={items.map((i) => i.id)} strategy={rectSortingStrategy}>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
          {items.map((it, i) => (
            <FileCard key={it.id} item={it} index={i} sortable={sortable && items.length > 1} onRemove={() => setItems(items.filter((x) => x.id !== it.id))} />
          ))}
          {multiple && (
            <button
              onClick={() => input.current?.click()}
              className="flex min-h-56 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-300 text-sm font-medium text-slate-500 transition hover:border-brand-400 hover:text-brand-600 dark:border-slate-700"
            >
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-brand-600 text-white shadow-lg shadow-brand-600/30">
                <Plus className="h-5 w-5" />
              </span>
              Add more files
              <input
                ref={input}
                type="file"
                hidden
                multiple
                accept={acceptAttr(accept)}
                onChange={(e) => {
                  const f = Array.from(e.target.files || []);
                  e.target.value = "";
                  if (f.length) onAdd(f);
                }}
              />
            </button>
          )}
        </div>
      </SortableContext>
    </DndContext>
  );
}
