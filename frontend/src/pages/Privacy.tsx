import { useEffect } from "react";
import { setHead } from "../api";
import { useApp } from "../store";

export default function Privacy() {
  const { catalog } = useApp();
  const brand = catalog?.brand || "PDFVana";
  const mins = Math.round((catalog?.limits.ttl_seconds || 3600) / 60);
  useEffect(() => {
    setHead(`Privacy & Security — ${brand}`, `How ${brand} protects your files: no account, automatic deletion, isolated processing, no trackers, open source.`);
  }, [brand]);
  const sections: [string, string][] = [
    ["No account, no profile", `${brand} works without sign-up. We don't ask for your name or e-mail, and we don't build a profile of what you do.`],
    ["Your files are deleted automatically", `Uploaded files are removed as soon as processing finishes. Results are kept for ${mins} minutes so you can download them, then permanently deleted. You can delete them immediately with "Delete now". Nothing survives a server restart.`],
    ["Processed in isolation", "Each task runs in its own temporary workspace. Files are never shared between users, never used to train AI models and never looked at by people."],
    ["Encrypted in transit", "Files travel encrypted between your browser and the server over HTTPS."],
    ["No trackers, no third parties", "There are no analytics, advertising or tracking scripts, and no third-party requests — even the fonts are served from this site."],
    ["Protected against misuse", "Web-page conversion blocks private and internal network addresses, upload sizes are capped and every task has a time limit."],
    ["Open source and self-hostable", "The full source code is public under the Apache-2.0 licence. Organisations with strict data policies can run the entire service inside their own network with one docker compose command."],
  ];
  return (
    <div className="mx-auto max-w-3xl py-16">
      <h1 className="text-4xl font-extrabold tracking-tight">Privacy & security</h1>
      <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">Your documents are yours. Here is exactly what happens to them.</p>
      <div className="mt-10 space-y-4">
        {sections.map(([h, p]) => (
          <div key={h} className="card p-6">
            <h2 className="font-bold">{h}</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{p}</p>
          </div>
        ))}
      </div>
      {catalog?.repo && (
        <p className="mt-8 text-sm text-slate-500">
          Found a security issue? Please report it privately — see <a className="text-brand-700 underline" href={`${catalog.repo}/security/policy`}>our security policy</a>.
        </p>
      )}
    </div>
  );
}
