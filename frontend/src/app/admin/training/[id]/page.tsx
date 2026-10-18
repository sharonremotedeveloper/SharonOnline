"use client";

import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApiData } from "@/hooks/useApiData";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState } from "@/components/ui/ErrorState";
import { TrainingModuleEditor } from "@/components/admin/TrainingModuleEditor";

export default function EditTrainingModulePage() {
  const { id } = useParams<{ id: string }>();
  const found = useApiData(() => api.getAdminTrainingModule(id), [id]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        backHref="/admin/training"
        backLabel="Back to training modules"
        eyebrow="TUTOR TRAINING"
        title={found.data?.title || "Edit module"}
      />
      {found.loading ? (
        <div className="h-64 animate-pulse rounded-3xl bg-white shadow-card" aria-busy="true" />
      ) : found.error || !found.data ? (
        <ErrorState error={found.error} title="We couldn't load this module" onRetry={found.reload} />
      ) : (
        <TrainingModuleEditor key={found.data.id} initial={found.data} />
      )}
    </div>
  );
}
