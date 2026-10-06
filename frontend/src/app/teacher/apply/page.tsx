"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/http";
import { useAuth } from "@/context/AuthContext";
import { buildApplicationPayload, isSpeedTestPassing, validateApplicationStep } from "@/lib/tutorApplication";

const ASSET_LABELS: Record<string, string> = {
  avatar: "Profile photo", accent_audio: "Accent audio", intro_video: "Intro video", tefl_certificate: "TEFL certificate", identity_document: "Identity document",
};
const DEFAULT_REQUIRED_KINDS = ["avatar", "accent_audio", "intro_video", "tefl_certificate", "identity_document"];

type Draft = { headline: string; bio: string; specialties: string[]; power: boolean; inverter: boolean; lte: boolean; download: number; upload: number; accepted: boolean; committed: string[] };
const EMPTY: Draft = { headline: "", bio: "", specialties: [], power: false, inverter: false, lte: false, download: 0, upload: 0, accepted: false, committed: [] };

export default function TutorApplicationPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [requiredKinds, setRequiredKinds] = useState<string[]>(DEFAULT_REQUIRED_KINDS);
  const [feedback, setFeedback] = useState<string[]>([]);
  const [accent, setAccent] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => { void (async () => {
    try {
      const [application, profile] = await Promise.all([api.getTeacherApplication(), api.getMyTeacherProfile()]);
      const requirements = application?.requirements || {};
      const kinds = Array.isArray(requirements.required_asset_kinds) ? requirements.required_asset_kinds : DEFAULT_REQUIRED_KINDS;
      setRequiredKinds(kinds);
      setDraft((old) => ({ ...old, headline: profile.headline || "", bio: profile.bio || "", specialties: profile.specialties || [], inverter: !!profile.has_inverter_backup, lte: !!profile.has_lte_failover }));
      setAccent(profile.accent_display || profile.accent || "Not yet assigned");
      setFeedback(profile.review_feedback?.requested_changes || []);
    } catch (err) { setMessage(errorMessage(err)); } finally { setLoading(false); }
  })(); }, []);

  const errors = useMemo(() => validateApplicationStep(step, { headline: draft.headline, bio: draft.bio, specialties: draft.specialties, committedKinds: draft.committed, requiredKinds, powerConfirmed: draft.power, download: draft.download, upload: draft.upload, accepted: draft.accepted }), [step, draft, requiredKinds]);
  const set = (patch: Partial<Draft>) => setDraft((old) => ({ ...old, ...patch }));

  async function saveProfile() {
    await api.updateMyTeacherProfile({ headline: draft.headline, bio: draft.bio, specialties: draft.specialties });
  }
  async function next() {
    if (errors.length) { setMessage(errors[0]); return; }
    setBusy(true); setMessage("");
    try {
      if (step === 1) await saveProfile();
      if (step === 3) { await api.updatePowerBackup({ has_inverter_backup: draft.inverter, has_lte_failover: draft.lte }); await api.updateTeacherApplication(buildApplicationPayload({ powerConfirmed: true })); }
      if (step === 4) await api.updateTeacherApplication(buildApplicationPayload({ download: draft.download, upload: draft.upload }));
      setStep(Math.min(5, step + 1));
    } catch (err) { setMessage(errorMessage(err)); } finally { setBusy(false); }
  }
  async function submit() {
    if (errors.length) { setMessage(errors[0]); return; }
    setBusy(true); setMessage("");
    try { await api.updateTeacherApplication(buildApplicationPayload({ accepted: true })); await api.submitTeacherApplication(); router.push("/teacher/application-submitted"); }
    catch (err) { setMessage(errorMessage(err)); } finally { setBusy(false); }
  }
  async function upload(kind: string, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file || !user) return;
    setBusy(true); setMessage("");
    try {
      const safe = file.name.replace(/[^a-zA-Z0-9._-]/g, "-");
      const key = `incoming/${user.id}/${crypto.randomUUID()}-${safe}`;
      const presigned = await api.presignTeacherAsset({ action: "upload", key, content_type: file.type || "application/octet-stream", size: file.size });
      const put = await fetch(presigned.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
      if (!put.ok) throw new Error("The upload could not be completed.");
      await api.commitTeacherAsset({ kind, key, etag: presigned.etag || "" });
      set({ committed: [...new Set([...draft.committed, kind])] });
    } catch (err) { setMessage(errorMessage(err, "Upload failed. Please try again.")); } finally { setBusy(false); }
  }
  async function speedTest() {
    setBusy(true); setMessage("");
    try {
      const downloadUrl = process.env.NEXT_PUBLIC_SPEED_TEST_DOWNLOAD_URL || "https://speed.cloudflare.com/__down?bytes=1000000";
      const uploadUrl = process.env.NEXT_PUBLIC_SPEED_TEST_UPLOAD_URL || "https://speed.cloudflare.com/__up";
      const bytes = 1000000; const start = performance.now(); const response = await fetch(`${downloadUrl}&cacheBust=${Date.now()}`, { cache: "no-store" }); await response.arrayBuffer();
      const down = (bytes * 8) / ((performance.now() - start) / 1000) / 1_000_000;
      const uploadBytes = new Uint8Array(250000); const uploadStart = performance.now(); const uploaded = await fetch(uploadUrl, { method: "POST", body: uploadBytes });
      if (!uploaded.ok) throw new Error("Upload speed test failed.");
      const up = (uploadBytes.byteLength * 8) / ((performance.now() - uploadStart) / 1000) / 1_000_000;
      set({ download: Number(down.toFixed(2)), upload: Number(up.toFixed(2)) });
      setMessage(isSpeedTestPassing(down, up) ? "Connection meets the 10/5 Mbps requirement." : "Connection is below the 10/5 Mbps requirement.");
    } catch (err) { setMessage(errorMessage(err, "Speed test failed. Please try again.")); } finally { setBusy(false); }
  }

  if (loading) return <main className="mx-auto max-w-3xl px-6 py-20">Loading your application…</main>;
  return <main className="min-h-screen bg-cream px-5 py-10 text-ink"><div className="mx-auto max-w-3xl">
    <p className="text-sm font-semibold uppercase tracking-[.18em] text-ink-muted">Tutor application</p>
    <h1 className="mt-3 font-['Lora'] text-4xl font-medium">Build your teaching profile</h1>
    {feedback.length > 0 && <aside className="mt-5 rounded-xl border border-warning-border bg-warning-surface p-4"><strong>Changes requested</strong><ul className="mt-2 list-disc pl-5">{feedback.map((item) => <li key={item}>{item}</li>)}</ul></aside>}
    <div className="mt-8 flex gap-2">{[1,2,3,4,5].map((number) => <div key={number} className={`h-2 flex-1 rounded-full ${number <= step ? "bg-cocoa" : "bg-cream-300"}`} />)}</div>
    <section className="mt-8 rounded-2xl bg-white p-6 shadow-sm">
      {step === 1 && <><h2 className="text-2xl font-semibold">Profile & bio</h2><p className="mt-2 text-ink-muted">Tell learners what makes your lessons effective.</p><div className="mt-6 grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-cream-deep p-3 text-sm"><span className="block text-sm text-ink-muted">Accent</span>{accent || "Not yet assigned"}</div><div className="rounded-lg bg-cream-deep p-3 text-sm"><span className="block text-sm text-ink-muted">Timezone</span>{user?.timezone || "UTC"}</div></div><input className="mt-3 w-full rounded-lg border border-strong p-3" placeholder="Profile headline" aria-label="Profile headline" value={draft.headline} onChange={(e) => set({ headline: e.target.value })} /><textarea className="mt-3 min-h-40 w-full rounded-lg border border-strong p-3" placeholder="Your teaching bio" aria-label="Your teaching bio" value={draft.bio} onChange={(e) => set({ bio: e.target.value })} /><input className="mt-3 w-full rounded-lg border border-strong p-3" placeholder="Specialties, separated by commas" aria-label="Specialties, separated by commas" value={draft.specialties.join(", ")} onChange={(e) => set({ specialties: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} /></>}
      {step === 2 && <><h2 className="text-2xl font-semibold">Your teaching assets</h2><p className="mt-2 text-ink-muted">Uploads are quarantined and checked before review.</p><div className="mt-6 space-y-3">{requiredKinds.map((kind) => <label key={kind} className="flex cursor-pointer items-center justify-between rounded-lg border border-strong p-4"><span>{ASSET_LABELS[kind] || kind.replaceAll("_", " ")}</span><span className={draft.committed.includes(kind) ? "text-success-hover" : "text-ink-muted"}>{draft.committed.includes(kind) ? "Uploaded" : "Choose file"}<input className="hidden" type="file" accept={kind === "intro_video" ? "video/*" : kind === "accent_audio" ? "audio/*" : "image/*,.pdf"} onChange={(e) => void upload(kind, e)} /></span></label>)}</div></>}
      {step === 3 && <><h2 className="text-2xl font-semibold">Power backup</h2><p className="mt-2 text-ink-muted">Lessons need a reliable continuity plan.</p><label className="mt-6 flex gap-3"><input type="checkbox" checked={draft.inverter} onChange={(e) => set({ inverter: e.target.checked })} /> I have inverter or battery backup.</label><label className="mt-3 flex gap-3"><input type="checkbox" checked={draft.lte} onChange={(e) => set({ lte: e.target.checked })} /> I have mobile/LTE failover.</label><label className="mt-6 flex gap-3"><input type="checkbox" checked={draft.power} onChange={(e) => set({ power: e.target.checked })} /> I confirm I can continue lessons during local outages.</label></>}
      {step === 4 && <><h2 className="text-2xl font-semibold">Network speed test</h2><p className="mt-2 text-ink-muted">We need at least 10 Mbps download and 5 Mbps upload for live lessons.</p><button className="min-h-11 inline-flex items-center mt-6 rounded-lg bg-cocoa px-5 py-3 font-semibold text-white disabled:opacity-50" disabled={busy} onClick={() => void speedTest()}>Run WebRTC network test</button><div className="mt-6 grid grid-cols-2 gap-4"><div className="rounded-lg bg-cream-deep p-4"><div className="text-sm text-ink-muted">Download</div><strong className="text-2xl">{draft.download.toFixed(2)} Mbps</strong></div><div className="rounded-lg bg-cream-deep p-4"><div className="text-sm text-ink-muted">Upload</div><strong className="text-2xl">{draft.upload.toFixed(2)} Mbps</strong></div></div></>}
      {step === 5 && <><h2 className="text-2xl font-semibold">Legal declarations</h2><p className="mt-2 text-ink-muted">Please confirm each statement before submitting.</p><label className="mt-6 flex gap-3"><input type="checkbox" checked={draft.accepted} onChange={(e) => set({ accepted: e.target.checked })} /> I confirm that my profile and teaching assets are accurate.</label><label className="mt-3 flex gap-3"><input type="checkbox" checked={draft.accepted} onChange={(e) => set({ accepted: e.target.checked })} /> I agree to the tutor terms and safeguarding requirements.</label></>}
      {message && <p className="mt-5 rounded-lg bg-warning-surface p-3 text-sm text-warning-hover">{message}</p>}
      <div className="mt-8 flex justify-between"><button className="min-h-11 inline-flex items-center rounded-lg border border-strong px-5 py-3" disabled={step === 1 || busy} onClick={() => setStep(step - 1)}>Back</button>{step < 5 ? <button className="min-h-11 inline-flex items-center rounded-lg bg-cocoa px-5 py-3 font-semibold text-white disabled:opacity-50" disabled={busy} onClick={() => void next()}>Save & continue</button> : <button className="min-h-11 inline-flex items-center rounded-lg bg-cocoa px-5 py-3 font-semibold text-white disabled:opacity-50" disabled={busy} onClick={() => void submit()}>Submit application</button>}</div>
    </section>
  </div></main>;
}
