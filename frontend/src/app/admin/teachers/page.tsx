"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Users,
  Search,
  CheckCircle2,
  Star,
  ExternalLink,
  ShieldCheck,
  MoreVertical,
  ArrowRight,
  Video,
} from "lucide-react";
import { api } from "@/lib/api";

export default function AdminTeachersPage() {
  const [tutors, setTutors] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadTutors() {
      try {
        const res = await api.getTutors();
        setTutors(res.results || []);
      } catch (e) {
        console.error("Failed to load tutors:", e);
      } finally {
        setLoading(false);
      }
    }
    loadTutors();
  }, []);

  const filtered = tutors.filter(
    (t) =>
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.accent.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold text-teal bg-teal/10 px-2 py-0.5 rounded-md">
              ACTIVE EDUCATORS
            </span>
            <span className="text-xs font-bold text-ink-muted">{tutors.length} Verified Tutors</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
            Tutor Roster &amp; Quality Telemetry
          </h1>
        </div>

        <Link
          href="/admin/teachers/vetting"
          className="px-5 py-2.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold rounded-xl shadow-xs flex items-center gap-2 transition-colors self-start sm:self-auto"
        >
          <span>Review Pending Auditions</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-3xl border border-divider shadow-xs flex items-center gap-3">
        <Search className="w-4 h-4 text-ink-muted ml-2" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter tutors by name, accent, or specialty..."
          className="flex-1 bg-transparent text-xs sm:text-sm text-ink focus:outline-none"
        />
      </div>

      {/* Roster Table */}
      <div className="bg-white rounded-3xl border border-divider shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] border-collapse text-xs">
            <thead>
              <tr className="bg-cream-surface border-b border-divider text-ink-muted uppercase font-bold tracking-wider text-left">
                <th className="py-3.5 px-6">Tutor Name</th>
                <th className="py-3.5 px-4">Accent / Dialect</th>
                <th className="py-3.5 px-4">Rating</th>
                <th className="py-3.5 px-4">Price / 25m</th>
                <th className="py-3.5 px-4">Verification</th>
                <th className="py-3.5 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-divider bg-white">
              {filtered.map((tutor) => (
                <tr key={tutor.id} className="hover:bg-cream-surface/40 transition-colors">
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-3">
                      <img
                        src={tutor.avatar}
                        alt={tutor.name}
                        className="w-10 h-10 rounded-2xl object-cover border border-divider"
                      />
                      <div>
                        <span className="font-extrabold text-sm text-ink block">{tutor.name}</span>
                        <span className="text-[11px] text-ink-muted">{tutor.bio?.slice(0, 45)}...</span>
                      </div>
                    </div>
                  </td>

                  <td className="py-4 px-4 font-semibold text-ink-muted">{tutor.accent}</td>

                  <td className="py-4 px-4">
                    <div className="flex items-center gap-1 font-bold text-ink">
                      <Star className="w-3.5 h-3.5 text-accent fill-accent" />
                      <span>{tutor.rating}</span>
                      <span className="text-[10px] text-ink-muted">({tutor.review_count})</span>
                    </div>
                  </td>

                  <td className="py-4 px-4 font-extrabold text-teal font-serif text-sm">
                    ${tutor.hourly_rate.toFixed(2)} USD
                  </td>

                  <td className="py-4 px-4">
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                      <ShieldCheck className="w-3 h-3 text-emerald-600" /> Active Verified
                    </span>
                  </td>

                  <td className="py-4 px-6 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        href={`/tutors/${tutor.slug || tutor.id}`}
                        target="_blank"
                        className="p-2 rounded-xl bg-cream-surface hover:bg-cream-deep text-ink-muted hover:text-ink transition-colors"
                        title="View Public Profile"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </Link>

                      <Link
                        href={`/admin/sessions/live`}
                        className="p-2 rounded-xl bg-teal/10 hover:bg-teal/20 text-teal transition-colors"
                        title="Live Activity Radar"
                      >
                        <Video className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
