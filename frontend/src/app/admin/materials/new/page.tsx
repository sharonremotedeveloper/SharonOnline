"use client";

import { PageHeader } from "@/components/ui/PageHeader";
import { MaterialEditor } from "@/components/admin/MaterialEditor";

export default function NewMaterialPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader backHref="/admin/materials" backLabel="Back to lesson materials" eyebrow="CURRICULUM" title="New material" />
      <MaterialEditor initial={null} />
    </div>
  );
}
