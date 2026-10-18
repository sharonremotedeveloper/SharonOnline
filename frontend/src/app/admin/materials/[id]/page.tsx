"use client";

import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApiData } from "@/hooks/useApiData";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState } from "@/components/ui/ErrorState";
import { MaterialEditor } from "@/components/admin/MaterialEditor";

export default function EditMaterialPage() {
  const { id } = useParams<{ id: string }>();
  const found = useApiData(() => api.getAdminMaterial(id), [id]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader backHref="/admin/materials" backLabel="Back to lesson materials" eyebrow="CURRICULUM" title={found.data?.title || "Edit material"} />
      {found.loading ? (
        <div className="h-64 animate-pulse rounded-3xl bg-white shadow-card" aria-busy="true" />
      ) : found.error || !found.data ? (
        <ErrorState error={found.error} title="We couldn't load this material" onRetry={found.reload} />
      ) : (
        <MaterialEditor key={found.data.id} initial={found.data} />
      )}
    </div>
  );
}
