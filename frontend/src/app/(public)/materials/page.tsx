"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { BookOpen, FileText, ArrowRight, Check, Search, Download } from "lucide-react";
import { Material } from "../../../types";
import { api } from "../../../lib/api";

const CATEGORIES = [
  { label: "All Curriculum", value: "" },
  { label: "Daily News & Discussion", value: "daily_news" },
  { label: "Business & Professional", value: "business" },
  { label: "FreeTalk Prompts", value: "freetalk" },
  { label: "Job Interview & Test Prep", value: "test_prep" },
];

const CEFR_LEVELS = ["All Levels", "A1", "A2", "B1", "B2", "C1", "C2"];

export default function MaterialsPage() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("");
  const [cefr, setCefr] = useState("All Levels");
  const [activeMaterial, setActiveMaterial] = useState<Material | null>(null);

  useEffect(() => {
    async function loadMaterials() {
      setLoading(true);
      try {
        const data = await api.getMaterials(
          category || undefined,
          cefr !== "All Levels" ? cefr : undefined
        );
        setMaterials(data);
      } catch (err) {
        console.error("Failed to load materials:", err);
      } finally {
        setLoading(false);
      }
    }
    loadMaterials();
  }, [category, cefr]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">Curriculum & Materials Library</h1>
        <p className="text-sm text-gray-600">
          Structured English lesson plans categorized by CEFR proficiency levels. Free to preview and study.
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white p-5 rounded-2xl shadow-card border border-gray-100 space-y-4">
        {/* Category Pills */}
        <div className="flex flex-wrap items-center gap-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.value}
              onClick={() => setCategory(cat.value)}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
                category === cat.value
                  ? "bg-brand-900 text-white shadow-sm"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* CEFR Level Selector */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-xs font-bold text-gray-500 mr-2">CEFR Level:</span>
          {CEFR_LEVELS.map((lvl) => (
            <button
              key={lvl}
              onClick={() => setCefr(lvl)}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                cefr === lvl
                  ? "bg-brand-100 text-brand-900 border border-brand-300"
                  : "text-gray-600 hover:bg-gray-50 border border-transparent"
              }`}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {/* Material Grid */}
      {loading ? (
        <div className="text-center py-20 text-gray-500 text-sm animate-pulse">
          Loading curriculum materials...
        </div>
      ) : materials.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-2xl border border-gray-100 p-8">
          <p className="text-gray-600 font-medium">No materials found matching this filter.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {materials.map((mat) => (
            <div
              key={mat.id}
              className="bg-white rounded-2xl border border-gray-100 shadow-card hover:shadow-card-hover transition-all p-6 flex flex-col justify-between space-y-4"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="px-2.5 py-1 rounded-md bg-brand-50 text-brand-900 font-extrabold text-xs border border-brand-100">
                    {mat.cefr_level}
                  </span>
                  <span className="text-[11px] font-medium text-gray-500">{mat.category_display}</span>
                </div>
                <h3 className="font-bold text-base text-gray-900 line-clamp-1">{mat.title}</h3>
                <p className="text-xs text-gray-600 line-clamp-2 leading-relaxed">{mat.description}</p>
              </div>

              <div className="pt-2 border-t border-gray-100 flex items-center justify-between">
                <button
                  onClick={() => setActiveMaterial(mat)}
                  className="text-xs font-bold text-brand-900 hover:text-brand-700 flex items-center gap-1"
                >
                  <FileText className="w-3.5 h-3.5" /> Read Lesson Plan
                </button>
                <Link
                  href="/tutors"
                  className="text-xs font-bold text-gold-600 hover:text-gold-500 flex items-center gap-1"
                >
                  Practice with Tutor <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Reading Reader Modal */}
      {activeMaterial && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 sm:p-8 space-y-6 max-h-[85vh] overflow-y-auto shadow-2xl relative">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded bg-brand-50 text-brand-900 font-bold text-xs">
                  {activeMaterial.cefr_level}
                </span>
                <span className="text-xs text-gray-500">{activeMaterial.category_display}</span>
              </div>
              <button
                onClick={() => setActiveMaterial(null)}
                className="text-gray-400 hover:text-gray-600 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <h2 className="text-2xl font-extrabold text-gray-900">{activeMaterial.title}</h2>
              <p className="text-xs text-gray-500">{activeMaterial.description}</p>

              {activeMaterial.content_html ? (
                <div
                  className="prose prose-sm max-w-none text-gray-800 text-xs sm:text-sm leading-relaxed border-t border-b border-gray-100 py-4"
                  dangerouslySetInnerHTML={{ __html: activeMaterial.content_html }}
                />
              ) : (
                <div className="p-6 bg-gray-50 rounded-xl text-center text-xs text-gray-500">
                  Full article content available in synchronous classroom view.
                </div>
              )}
            </div>

            <div className="pt-2 flex justify-between items-center">
              <button
                onClick={() => setActiveMaterial(null)}
                className="px-4 py-2 border border-gray-200 rounded-xl text-xs font-semibold text-gray-700 hover:bg-gray-50"
              >
                Close
              </button>
              <Link
                href="/tutors"
                className="px-5 py-2.5 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold flex items-center gap-2"
              >
                Book Tutor for this Lesson <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
