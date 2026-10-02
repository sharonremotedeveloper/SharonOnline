import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-xl mx-auto px-4 py-24 text-center space-y-4">
      <p className="text-xs font-bold uppercase tracking-wider text-primary">404</p>
      <h1 className="text-3xl font-extrabold text-ink font-serif">We couldn&apos;t find that page</h1>
      <p className="text-sm text-ink-muted">The link may be out of date, or the page may have moved.</p>
      <Link
        href="/"
        className="inline-block px-5 py-2.5 rounded-md bg-primary text-white text-sm font-medium hover:bg-primary-hover transition-colors"
      >
        Back to home
      </Link>
    </div>
  );
}
