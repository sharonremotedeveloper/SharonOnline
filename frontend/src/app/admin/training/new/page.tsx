"use client";

import { PageHeader } from "@/components/ui/PageHeader";
import { TrainingModuleEditor } from "@/components/admin/TrainingModuleEditor";

export default function NewTrainingModulePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader backHref="/admin/training" backLabel="Back to training modules" eyebrow="TUTOR TRAINING" title="New module" />
      <TrainingModuleEditor initial={null} />
    </div>
  );
}
