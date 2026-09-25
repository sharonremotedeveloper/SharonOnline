"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Search, Star, ShieldCheck, Video, Clock, Filter, ArrowRight } from "lucide-react";
import { Teacher } from "../../../types";
import { api } from "../../../lib/api";

const ACCENTS = [
  { label: "All Accents", value: "" },
  { label: "🇿🇦 South African", value: "ZA" },
  { label: "🇬🇧 British", value: "UK" },
  { label: "🇺🇸 American", value: "US" },
  { label: "🌐 International", value: "OTHER" },
];

const SPECIALTIES = [
  "All Specialties",
  "FreeTalk",
  "Business English",
  "Daily News",
  "IELTS/TOEIC",
  "Pronunciation"
];

export default function TutorsPage() {
  const [tutors, setTutors] = useState<Teacher[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [accent, setAccent] = useState("");
  const [specialty, setSpecialty] = useState("All Specialties");

  useEffect(() => {
    async function loadTutors() {
      setLoading(true);
      try {
        const data = await api.getTeachers({
          accent: accent || undefined,
          specialty: specialty !== "All Specialties" ? specialty : undefined,
          search: search || undefined,
        });
        setTutors(data);
      } catch (err) {
        console.error("Failed to load tutors:", err);
      } finally {
        setLoading(false);
      }
    }
    loadTutors();
  }, [accent, specialty, search]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Page Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">Find Your English Tutor</h1>
        <p className="text-sm text-gray-600">
          Book 1-on-1 private lessons in 25-minute increments. Filter by accent, specialty, and availability.
        </p>
      </div>

      {/* Filter Controls */}
      <div className="bg-white p-5 rounded-2xl shadow-card border border-gray-100 space-y-4">
        {/* Search Bar */}
        <div className="relative">
          <Search className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search by tutor name, keyword, or teaching specialty..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-brand-700 focus:ring-1 focus:ring-brand-700"
          />
        </div>

        {/* Accent Pills */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-xs font-bold text-gray-500 mr-2 flex items-center gap-1">
            <Filter className="w-3.5 h-3.5" /> Accent:
          </span>
          {ACCENTS.map((item) => (
            <button
              key={item.value}
              onClick={() => setAccent(item.value)}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
                accent === item.value
                  ? "bg-brand-900 text-white shadow-sm"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Specialty Filter */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-xs font-bold text-gray-500 mr-2">Focus:</span>
          {SPECIALTIES.map((spec) => (
            <button
              key={spec}
              onClick={() => setSpecialty(spec)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                specialty === spec
                  ? "bg-brand-100 text-brand-900 font-bold border border-brand-300"
                  : "text-gray-600 hover:bg-gray-50 border border-transparent"
              }`}
            >
              {spec}
            </button>
          ))}
        </div>
      </div>

      {/* Tutor Grid */}
      {loading ? (
        <div className="text-center py-20 text-gray-500 text-sm animate-pulse">
          Loading vetted tutors...
        </div>
      ) : tutors.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-2xl border border-gray-100 p-8">
          <p className="text-gray-600 font-medium">No tutors found matching your current filter criteria.</p>
          <button
            onClick={() => { setAccent(""); setSpecialty("All Specialties"); setSearch(""); }}
            className="mt-3 text-xs font-bold text-brand-700 hover:underline"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {tutors.map((tutor) => (
            <div
              key={tutor.id}
              className="bg-white rounded-2xl border border-gray-100 shadow-card hover:shadow-card-hover transition-all flex flex-col justify-between overflow-hidden group"
            >
              {/* Card Header & Avatar */}
              <div className="p-6 space-y-4">
                <div className="flex items-start gap-4">
                  <div className="relative w-16 h-16 rounded-full overflow-hidden bg-brand-50 flex-shrink-0 border-2 border-brand-100">
                    {tutor.avatar_url ? (
                      <img src={tutor.avatar_url} alt={tutor.full_name} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center font-bold text-xl text-brand-800">
                        {tutor.first_name[0]}
                      </div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <h3 className="font-bold text-base text-gray-900 truncate">{tutor.full_name}</h3>
                      {tutor.is_verified && (
                        <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                      )}
                    </div>
                    <div className="text-xs text-gray-500 font-medium mt-0.5">
                      {tutor.accent === 'ZA' ? '🇿🇦 South African' : tutor.accent === 'UK' ? '🇬🇧 British' : tutor.accent === 'US' ? '🇺🇸 American' : '🌐 International'}
                    </div>
                    <div className="flex items-center gap-2 mt-1.5 text-xs">
                      <span className="flex items-center text-amber-500 font-bold">
                        <Star className="w-3.5 h-3.5 fill-current mr-0.5" />
                        {Number(tutor.rating_avg).toFixed(2)}
                      </span>
                      <span className="text-gray-400">({tutor.rating_count} lessons)</span>
                    </div>
                  </div>
                </div>

                {/* Headline & Bio Preview */}
                <p className="text-xs font-semibold text-brand-900 line-clamp-1">{tutor.headline}</p>
                <p className="text-xs text-gray-600 line-clamp-2 leading-relaxed">{tutor.bio}</p>

                {/* Specialty Tags */}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {tutor.specialties.slice(0, 3).map((tag) => (
                    <span key={tag} className="px-2 py-0.5 rounded-md bg-gray-100 text-gray-700 text-[11px] font-medium">
                      {tag}
                    </span>
                  ))}
                  {tutor.specialties.length > 3 && (
                    <span className="px-1.5 py-0.5 text-gray-400 text-[11px]">+{tutor.specialties.length - 3}</span>
                  )}
                </div>
              </div>

              {/* Card Footer / Booking Trigger */}
              <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
                <div>
                  <span className="text-lg font-extrabold text-gray-900">${Number(tutor.price_per_25min_usd).toFixed(2)}</span>
                  <span className="text-[11px] text-gray-500 font-medium ml-1">/ 25 min</span>
                </div>
                <Link
                  href={`/tutors/${tutor.id}`}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold transition-all shadow-sm group-hover:bg-gold-500 group-hover:text-brand-950"
                >
                  Book Slot <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
