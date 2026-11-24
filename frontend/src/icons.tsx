import {
  AppWindow, Archive, Camera, Clapperboard, Crop, EyeOff, File, FileCode2, FileOutput, FileText, Film, GitCompare, Globe,
  Hash, Image, Info, Layers, LayoutGrid, Lock, LockOpen, Merge, Minimize2, Music, PanelTop, PenLine, PenTool, Presentation,
  Repeat2, RotateCw, Scaling, ScanText, Sheet, ShieldCheck, Split, Stamp, Table2, Trash2, Type, Workflow, Wrench,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  workflow: Workflow, convert: Repeat2, merge: Merge, split: Split, remove: Trash2, extract: FileOutput,
  organize: LayoutGrid, rotate: RotateCw, compress: Minimize2, repair: Wrench, ocr: ScanText, archive: Archive,
  word: FileText, powerpoint: Presentation, excel: Sheet, image: Image, html: Globe, file: File, text: Type,
  watermark: Stamp, numbers: Hash, header: PanelTop, sign: PenLine, crop: Crop, flatten: Layers, info: Info,
  lock: Lock, unlock: LockOpen, redact: EyeOff, shield: ShieldCheck, compare: GitCompare, markdown: FileCode2,
  video: Film, audio: Music, gif: Clapperboard, vector: PenTool, favicon: AppWindow, resize: Scaling, data: Table2,
  screenshot: Camera,
};

const CATEGORY_TONE: Record<string, string> = {
  workflow: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  organize: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300",
  optimize: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  "to-pdf": "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  "from-pdf": "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  image: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  media: "bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300",
  edit: "bg-pink-100 text-pink-700 dark:bg-pink-500/15 dark:text-pink-300",
  security: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  intelligence: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300",
};

const ICON_TONE: Record<string, string> = {
  word: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  powerpoint: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300",
  excel: "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300",
  data: "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300",
};

export function ToolIcon({ icon, category, size = "md" }: { icon: string; category: string; size?: "sm" | "md" | "lg" }) {
  const Icon = ICONS[icon] || File;
  const tone = ICON_TONE[icon] || CATEGORY_TONE[category] || CATEGORY_TONE.organize;
  const box = size === "lg" ? "h-14 w-14 rounded-2xl" : size === "sm" ? "h-8 w-8 rounded-lg" : "h-11 w-11 rounded-xl";
  const ic = size === "lg" ? "h-7 w-7" : size === "sm" ? "h-4 w-4" : "h-5 w-5";
  return (
    <span className={`inline-flex shrink-0 items-center justify-center ${box} ${tone}`}>
      <Icon className={ic} strokeWidth={2} />
    </span>
  );
}

/** GitHub mark (brand icons are not part of the icon set). */
export function GithubMark({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.73.5.5 5.74.5 12.02c0 5.1 3.29 9.42 7.86 10.95.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.36-3.87-1.36-.52-1.34-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.76 2.7 1.25 3.36.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.53 11.53 0 0 0 23.5 12.02C23.5 5.74 18.27.5 12 .5z" />
    </svg>
  );
}

export function Logo({ brand, compact = false }: { brand: string; compact?: boolean }) {
  const pdf = brand.startsWith("PDF") ? "PDF" : "";
  const rest = pdf ? brand.slice(3) : brand;
  return (
    <span className="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" className="h-8 w-8" width={32} height={32} />
      {!compact && (
        <span className="text-lg font-extrabold tracking-tight">
          {pdf && <span className="text-brand-700 dark:text-brand-400">{pdf}</span>}
          {rest}
        </span>
      )}
    </span>
  );
}
