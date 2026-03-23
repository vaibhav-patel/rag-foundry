import { Link, Outlet } from "react-router-dom";

export function AdminLayout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 px-6 py-4 flex gap-4">
        <span className="font-semibold text-emerald-400">rag-foundry</span>
        <Link className="text-slate-300 hover:text-white" to="/">
          KB wizard
        </Link>
        <Link className="text-slate-300 hover:text-white" to="/playground">
          Playground
        </Link>
      </header>
      <main className="p-6 max-w-5xl">
        <Outlet />
      </main>
    </div>
  );
}
