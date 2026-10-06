"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Users,
  Search,
  BookOpen,
  Edit3,
  Save,
  CheckCircle2,
  Lock,
  Plus,
  X,
  ChevronLeft,
  Calendar,
  AlertCircle,
  FileText,
  Sparkles,
} from "lucide-react";
import { teacherCrmApi } from "@/lib/api";
import { TeacherStudentDossierItem } from "@/types/student";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

export default function TeacherStudentsCRMPage() {
  const [students, setStudents] = useState<TeacherStudentDossierItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [editingStudentId, setEditingStudentId] = useState<string | null>(null);
  const [draftNotes, setDraftNotes] = useState("");
  const [draftMistake, setDraftMistake] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function loadCRM() {
      setIsLoading(true);
      setLoadError(null);
      try {
        const data = await teacherCrmApi.getTeacherStudentsDossier();
        if (!cancelled) setStudents(data);
      } catch (err) {
        console.error("Failed to load teacher students CRM:", err);
        if (!cancelled) {
          setStudents([]);
          setLoadError(err);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    loadCRM();
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  const handleStartEdit = (student: TeacherStudentDossierItem) => {
    setEditingStudentId(student.student_id);
    setDraftNotes(student.private_pedagogical_notes);
    setSaveError(null);
  };

  const handleSaveNotes = async (studentId: string) => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await teacherCrmApi.updateTeacherStudentDossier(studentId, draftNotes);
      const name = students.find((s) => s.student_id === studentId)?.student_name;
      setStudents((prev) =>
        prev.map((s) => (s.student_id === studentId ? { ...s, private_pedagogical_notes: draftNotes } : s))
      );
      setEditingStudentId(null);
      setSaveSuccessMsg(`Notes updated for ${name}!`);
      setTimeout(() => setSaveSuccessMsg(null), 3000);
    } catch (err) {
      console.error("Failed to save dossier notes:", err);
      setSaveError(err);
    } finally {
      setIsSaving(false);
    }
  };

  // Persist the slip list to the server first; local state only changes once the save succeeded.
  const persistMistakes = async (student: TeacherStudentDossierItem, next: string[]) => {
    setSaveError(null);
    try {
      await teacherCrmApi.updateTeacherStudentDossier(student.student_id, student.private_pedagogical_notes, next);
      setStudents((prev) =>
        prev.map((s) => (s.student_id === student.student_id ? { ...s, common_grammar_mistakes: next } : s))
      );
      return true;
    } catch (err) {
      console.error("Failed to save grammar slips:", err);
      setSaveError(err);
      return false;
    }
  };

  const handleAddMistake = async (studentId: string) => {
    const student = students.find((s) => s.student_id === studentId);
    if (!student || !draftMistake.trim()) return;
    const ok = await persistMistakes(student, [...student.common_grammar_mistakes, draftMistake.trim()]);
    if (ok) setDraftMistake("");
  };

  const handleRemoveMistake = async (studentId: string, indexToRemove: number) => {
    const student = students.find((s) => s.student_id === studentId);
    if (!student) return;
    await persistMistakes(
      student,
      student.common_grammar_mistakes.filter((_, idx) => idx !== indexToRemove)
    );
  };

  const filteredStudents = students.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      s.student_name.toLowerCase().includes(q) ||
      s.student_country.toLowerCase().includes(q) ||
      s.target_level.toLowerCase().includes(q)
    );
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8 animate-fade-in">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Link
              href="/teacher/dashboard"
              className="p-1.5 text-ink-400 hover:text-ink-900 hover:bg-cream-100 rounded-xl transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-ink-900 tracking-tight">
              Student Pedagogical Dossier CRM
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-ink-600 mt-1 pl-8">
            Confidential tutor notes, student learning goals, recurring grammar slips, and lesson histories.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="bg-cocoa-50 border border-cocoa-200/80 px-3.5 py-1.5 rounded-xl flex items-center gap-1.5 text-xs text-cocoa-900 font-medium">
            <Lock className="w-3.5 h-3.5 text-cocoa-700" /> Private to Tutor
          </div>
          <Link
            href="/teacher/dashboard"
            className="px-4 py-2 bg-cream-100 hover:bg-cream-200 text-ink-800 text-xs font-semibold rounded-xl transition-colors"
          >
            Tutor Dashboard
          </Link>
        </div>
      </div>

      <InlineError error={saveError} />

      {saveSuccessMsg && (
        <div className="bg-success-surface border border-success-border text-success-hover p-4 rounded-2xl flex items-center gap-2 text-xs font-semibold animate-scale-up">
          <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
          <span>{saveSuccessMsg}</span>
        </div>
      )}

      {/* Search Bar */}
      <div className="bg-white rounded-2xl border border-cream-200 p-4 shadow-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search students by name, country, or CEFR level..."
            className="w-full pl-10 pr-4 py-2 bg-cream-50/50 border border-cream-200 rounded-xl text-xs sm:text-sm text-ink-900 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
          />
        </div>

        <div className="text-xs text-ink-500 font-medium">
          Total Regular Students: <strong className="text-ink-800">{loadError ? "—" : students.length}</strong>
        </div>
      </div>

      {/* Student Dossier Cards */}
      {isLoading ? (
        <div className="bg-white rounded-3xl border border-cream-200 p-10 text-center text-sm text-ink-500 font-medium">
          Loading your students...
        </div>
      ) : loadError ? (
        <ErrorState error={loadError} title="We couldn't load your students" onRetry={() => setReloadTick((t) => t + 1)} />
      ) : filteredStudents.length === 0 ? (
        <div className="bg-white rounded-3xl border border-cream-200 p-10 text-center text-sm text-ink-500">
          {students.length === 0
            ? "You don't have any students yet. They'll appear here after their first lesson with you."
            : "No students match your search."}
        </div>
      ) : (
      <div className="grid grid-cols-1 gap-6">
        {filteredStudents.map((student) => (
          <div
            key={student.id}
            className="bg-white rounded-3xl border border-cream-200 shadow-sm overflow-hidden p-6 sm:p-8 space-y-6 hover:shadow-md transition-shadow"
          >
            {/* Header: Student Bio & Metas */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-cream-100 pb-5">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-2xl bg-cocoa-100/70 border border-cocoa-200 text-cocoa-800 flex items-center justify-center font-bold text-lg">
                  {student.student_name.slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-black text-ink-900">{student.student_name}</h3>
                    <span className="text-xs bg-cocoa-50 text-cocoa-800 border border-cocoa-200 font-bold px-2.5 py-0.5 rounded-full">
                      CEFR {student.target_level}
                    </span>
                  </div>
                  <div className="text-xs text-ink-500 mt-0.5 flex items-center gap-3">
                    <span>{student.student_country}</span>
                    <span>•</span>
                    <span>{student.student_email}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3 self-start sm:self-auto text-xs">
                <div className="bg-cream-50 border border-cream-200 px-3.5 py-1.5 rounded-xl text-center">
                  <span className="text-ink-400 block text-xs uppercase font-bold">Lessons Taken</span>
                  <strong className="text-ink-900 text-sm font-extrabold">{student.lessons_completed_count}</strong>
                </div>
                <div className="bg-cream-50 border border-cream-200 px-3.5 py-1.5 rounded-xl text-center">
                  <span className="text-ink-400 block text-xs uppercase font-bold">Last Lesson</span>
                  <strong className="text-ink-900 text-xs font-semibold">{student.last_lesson_date}</strong>
                </div>
              </div>
            </div>

            {/* Pedagogical Notes & Mistakes */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Private Notes */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-ink-700 uppercase tracking-wider">
                    <FileText className="w-4 h-4 text-cocoa-600" />
                    <span>Private Pedagogical Notes</span>
                  </div>
                  {editingStudentId !== student.student_id ? (
                    <button
                      onClick={() => handleStartEdit(student)}
                      className="text-xs font-semibold text-cocoa-700 hover:text-cocoa-900 flex items-center gap-1"
                    >
                      <Edit3 className="w-3 h-3" /> Edit Notes
                    </button>
                  ) : (
                    <button
                      onClick={() => setEditingStudentId(null)}
                      className="text-xs text-ink-500 hover:text-ink-800"
                    >
                      Cancel
                    </button>
                  )}
                </div>

                {editingStudentId === student.student_id ? (
                  <div className="space-y-2">
                    <textarea
                      value={draftNotes}
                      onChange={(e) => setDraftNotes(e.target.value)}
                      rows={4}
                      className="w-full text-xs rounded-xl border border-cream-200 p-3 bg-cream-50/50 text-ink-900 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
                    />
                    <div className="flex justify-end">
                      <button
                        onClick={() => handleSaveNotes(student.student_id)}
                        disabled={isSaving}
                        className="inline-flex items-center gap-1 px-4 py-2 bg-cocoa-600 hover:bg-cocoa-700 disabled:opacity-50 text-white font-bold text-xs rounded-xl shadow-xs"
                      >
                        <Save className="w-3.5 h-3.5" /> Save
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="bg-cream-50/60 border border-cream-200/80 rounded-2xl p-4 text-xs text-ink-800 leading-relaxed min-h-[96px]">
                    {student.private_pedagogical_notes}
                  </div>
                )}
              </div>

              {/* Recurring Grammar & Pronunciation Slips */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold text-ink-700 uppercase tracking-wider">
                  <AlertCircle className="w-4 h-4 text-warning" />
                  <span>Recurring Grammar & Pronunciation Slips</span>
                </div>

                <div className="bg-warning-surface/30 border border-warning-border/60 rounded-2xl p-4 space-y-3 min-h-[96px]">
                  <div className="flex flex-wrap gap-1.5">
                    {student.common_grammar_mistakes.map((slip, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1 px-2.5 py-1 bg-white border border-warning-border text-warning-hover rounded-lg text-xs font-medium shadow-2xs"
                      >
                        {slip}
                        <button
                          type="button"
                          onClick={() => handleRemoveMistake(student.student_id, idx)}
                          className="text-warning hover:text-warning-hover ml-0.5"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>

                  <div className="flex items-center gap-2 pt-1 border-t border-warning-surface">
                    <input
                      type="text"
                      value={draftMistake}
                      onChange={(e) => setDraftMistake(e.target.value)}
                      placeholder="Add recurring slip (e.g. 'Article omission')..."
                      className="flex-1 text-xs rounded-lg border border-cream-200 px-3 py-1.5 bg-white text-ink-900 focus:outline-none focus:ring-1 focus:ring-cocoa-500"
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddMistake(student.student_id);
                        }
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => handleAddMistake(student.student_id)}
                      className="p-1.5 bg-cocoa-600 hover:bg-cocoa-700 text-white rounded-lg text-xs"
                      title="Add slip"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
      )}
    </div>
  );
}
