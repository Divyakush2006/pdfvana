import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/** Keeps a rendering error from ever leaving the user on a blank page. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
    // A new deployment can make old code chunks disappear: reload once to pick up the new version.
    if (/Loading chunk|dynamically imported module|Importing a module script failed/i.test(String(error?.message))) {
      try {
        if (!sessionStorage.getItem("reloaded-after-error")) {
          sessionStorage.setItem("reloaded-after-error", "1");
          window.location.reload();
        }
      } catch {
        /* storage unavailable */
      }
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
          <AlertTriangle className="h-8 w-8" />
        </div>
        <h1 className="text-2xl font-bold">Something went wrong on this page</h1>
        <p className="mt-2 text-slate-500">Your files are safe. Reload the page to continue.</p>
        <div className="mt-6 flex justify-center gap-3">
          <button className="btn-primary" onClick={() => window.location.reload()}>
            <RotateCcw className="h-4 w-4" /> Reload
          </button>
          <a className="btn-outline" href="/">All tools</a>
        </div>
      </div>
    );
  }
}
