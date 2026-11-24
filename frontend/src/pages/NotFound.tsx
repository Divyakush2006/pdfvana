import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="py-32 text-center">
      <div className="text-7xl font-extrabold text-brand-600">404</div>
      <h1 className="mt-4 text-2xl font-bold">This page doesn't exist</h1>
      <p className="mt-2 text-slate-500">The tool may have moved. Find it on the home page.</p>
      <Link to="/" className="btn-primary mt-8">See all tools</Link>
    </div>
  );
}
