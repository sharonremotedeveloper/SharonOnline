export const APPLICATION_MIN_DOWNLOAD_MBPS = 10;
export const APPLICATION_MIN_UPLOAD_MBPS = 5;

export function isSpeedTestPassing(download: number, upload: number): boolean {
  return Number.isFinite(download) && Number.isFinite(upload) && download >= APPLICATION_MIN_DOWNLOAD_MBPS && upload >= APPLICATION_MIN_UPLOAD_MBPS;
}

export function validateApplicationStep(step: number, input: {
  headline?: string;
  bio?: string;
  specialties?: string[];
  committedKinds?: string[];
  requiredKinds?: string[];
  powerConfirmed?: boolean;
  download?: number;
  upload?: number;
  accepted?: boolean;
}): string[] {
  if (step === 1) return [
    ...(input.headline?.trim() ? [] : ["Add a profile headline."]),
    ...(input.bio?.trim() ? [] : ["Tell learners about your teaching experience."]),
    ...(input.specialties?.length ? [] : ["Choose at least one specialty."]),
  ];
  if (step === 2) return (input.requiredKinds || []).filter((kind) => !(input.committedKinds || []).includes(kind)).map((kind) => `Upload your ${kind.replaceAll("_", " ")}.`);
  if (step === 3) return input.powerConfirmed ? [] : ["Confirm that you have a power-backup plan."];
  if (step === 4) return isSpeedTestPassing(Number(input.download), Number(input.upload)) ? [] : ["Your connection must reach at least 10 Mbps download and 5 Mbps upload."];
  if (step === 5) return input.accepted ? [] : ["Accept the legal declarations to submit your application."];
  return [];
}

export function buildApplicationPayload(input: { download?: number; upload?: number; powerConfirmed?: boolean; accepted?: boolean }) {
  return {
    ...(input.download !== undefined && input.upload !== undefined ? { speed_test: { download_mbps: input.download.toFixed(2), upload_mbps: input.upload.toFixed(2) } } : {}),
    ...(input.powerConfirmed !== undefined ? { confirm_power_backup: input.powerConfirmed } : {}),
    ...(input.accepted !== undefined ? { accept_declaration: input.accepted } : {}),
  };
}
