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
