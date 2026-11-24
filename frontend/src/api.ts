export type Choice = { value: string; label: string };

export type Option = {
  id: string;
  label: string;
  type: "select" | "number" | "text" | "password" | "checkbox" | "range" | "color" | "textarea" | "multiselect" | "position" | "pages";
  default: unknown;
  choices: Choice[] | null;
  help: string | null;
  min: number | null;
  max: number | null;
  step: number | null;
  placeholder: string | null;
  show_if: Record<string, unknown[]> | null;
};

export type ExtraFile = { id: string; label: string; accept: string[]; required: boolean };

export type Tool = {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  accept: string[];
  multiple: boolean;
  min_files: number;
  max_files: number | null;
  options: Option[];
  extra_files: ExtraFile[];
  cta: string;
  ui: "organize" | "sign" | "compare" | "url" | "studio" | "convert" | null;
  badge: string | null;
  keywords: string;
  seo: Seo;
};

export type Seo = {
  title: string;
  description: string;
  h1: string;
  intro: string;
  steps: string[];
  faqs: { q: string; a: string }[];
};

export type Pair = Seo & { slug: string; from: string; to: string; accept: string[] };

export type Catalog = {
  brand: string;
  version: string;
  repo: string;
  site: string;
  categories: { id: string; name: string }[];
  tools: Tool[];
  formats: Record<string, { label: string; category: string }>;
  targets: Record<string, string[]>;
  input_categories: Record<string, string>;
  pairs: Pair[];
  ocr_languages: Choice[];
  limits: { max_file_mb: number; max_total_mb: number; max_files: number; ttl_seconds: number };
};

export function fileCategory(catalog: Catalog, name: string): string {
  return catalog.input_categories[extOf(name)] || "document";
}

/** Output formats every given file can be converted to. */
export function allowedTargets(catalog: Catalog, names: string[]): string[] {
  if (!names.length) return Object.keys(catalog.formats);
  const sets = names.map((n) => new Set(catalog.targets[fileCategory(catalog, n)] || []));
  return Object.keys(catalog.formats).filter((f) => sets.every((s) => s.has(f)));
}

export function setHead(title: string, description?: string, canonical?: string) {
  document.title = title;
  const set = (selector: string, attr: string, value: string, create: () => HTMLElement) => {
    let el = document.head.querySelector(selector) as HTMLElement | null;
    if (!el) {
      el = create();
      document.head.appendChild(el);
    }
    el.setAttribute(attr, value);
  };
  if (description)
    set('meta[name="description"]', "content", description, () => Object.assign(document.createElement("meta"), { name: "description" }));
  if (canonical)
    set('link[rel="canonical"]', "href", canonical, () => Object.assign(document.createElement("link"), { rel: "canonical" }));
}

export type JobState = {
  id: string;
  tool: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  stage: string;
  message: string;
  error: string;
  expires_in: number;
  input_bytes: number;
  seconds?: number;
  result?: { name: string; size: number };
};

export async function fetchCatalog(): Promise<Catalog> {
  const r = await fetch("/api/tools");
  if (!r.ok) throw new Error("Could not load tools");
  return r.json();
}

export function createJob(
  tool: string,
  files: File[],
  options: Record<string, unknown>,
  extras: Record<string, File | null>,
  onUpload: (fraction: number) => void,
): Promise<JobState> {
  const form = new FormData();
  form.append("tool", tool);
  form.append("options", JSON.stringify(options));
  files.forEach((f) => form.append("files", f, f.name));
  Object.entries(extras).forEach(([k, f]) => f && form.append(`extra_${k}`, f, f.name));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.upload.onprogress = (e) => e.lengthComputable && onUpload(e.loaded / e.total);
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body?.error || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error — check your connection and try again."));
    xhr.send(form);
  });
}

export async function getJob(id: string): Promise<JobState> {
  const r = await fetch(`/api/jobs/${id}`);
  const body = await r.json();
  if (!r.ok) throw new Error(body?.error || "Job not found");
  return body;
}

export async function deleteJob(id: string) {
  await fetch(`/api/jobs/${id}`, { method: "DELETE" });
}

export const downloadUrl = (id: string) => `/api/jobs/${id}/download`;

export function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export const extOf = (name: string) => (name.split(".").pop() || "").toLowerCase();
