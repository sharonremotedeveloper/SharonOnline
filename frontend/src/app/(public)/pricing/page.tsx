import { PricingTable } from "@/components/public/PricingTable";
import { PAYMENTS_ENABLED } from "@/lib/paymentsEnabled";

export default function PricingPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-12">
      {/* Header */}
      <div className="text-center max-w-3xl mx-auto space-y-3">
        <h1 className="text-4xl font-extrabold text-cocoa-900 tracking-tight">
          Transparent, Flexible Pricing
        </h1>
        <p className="text-base text-cocoa-600">
          {PAYMENTS_ENABLED
            ? "No mandatory monthly recurring subscriptions. Pay per lesson or save with lesson credit packs."
            : "Browse our lesson prices. New purchases are temporarily unavailable."}
        </p>
      </div>

      {/* Every price below is loaded from the platform price list, never typed into the page. */}
      <PricingTable />
    </div>
  );
}
