export default function Loading() {
  return (
    <div className="max-w-7xl mx-auto px-4 py-20 flex items-center justify-center" role="status" aria-live="polite">
      <div className="w-8 h-8 border-4 border-divider border-t-primary rounded-full animate-spin" aria-hidden="true" />
      <span className="sr-only">Loading...</span>
    </div>
  );
}
