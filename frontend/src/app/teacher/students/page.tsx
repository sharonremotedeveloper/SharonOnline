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

export default function TeacherStudentsCRMPage() {
  const [students, setStudents] = useState<TeacherStudentDossierItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [editingStudentId, setEditingStudentId] = useState<string | null>(null);
  const [draftNotes, setDraftNotes] = useState("");
  const [draftMistake, setDraftMistake] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    async function loadCRM() {
      try {
        const data = await teacherCrmApi.getTeacherStudentsDossier();
        setStudents(data);
      } catch (err) {
        console.error("Failed to load teacher students CRM:", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadCRM();
  }, []);

  const handleStartEdit = (student: TeacherStudentDossierItem) => {
    setEditingStudentId(student.student_id);
    setDraftNotes(student.private_pedagogical_notes);
  };

  const handleSaveNotes = async (studentId: string) => {
    setIsSaving(true);
    try {
      await teacherCrmApi.updateTeacherStudentDossier(studentId, draftNotes);
      setStudents((prev) =>
        prev.map((s) => (s.student_id === studentId ? { ...s, private_pedagogical_notes: draftNotes } : s))
      );
      setEditingStudentId(null);
      setSaveSuccessMsg(`Notes updated for ${students.find((s) => s.student_id === studentId)?.student_name}!`);
      setTimeout(() => setSaveSuccessMsg(null), 3000);
    } catch (err) {
      console.error("Failed to save dossier notes:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddMistake = (studentId: string) => {
    if (!draftMistake.trim()) return;
    setStudents((prev) =>
      prev.map((s) =>
        s.student_id === studentId
          ? {
              ...s,
              common_grammar_mistakes: [...s.common_grammar_mistakes, draftMistake.trim()],
            }
          : s
      )
    );
    setDraftMistake("");
  };

  const handleRemoveMistake = (studentId: string, indexToRemove: number) => {
    setStudents((prev) =>
      prev.map((s) =>
        s.student_id === studentId
          ? {
              ...s,
              common_grammar_mistakes: s.common_grammar_mistakes.filter((_, idx) => idx !== indexToRemove),
            }
          : s
      )
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
          <div className="bg-teal-50 border border-teal-200/80 px-3.5 py-1.5 rounded-xl flex items-center gap-1.5 text-xs text-teal-900 font-medium">
            <Lock className="w-3.5 h-3.5 text-teal-700" /> Private to Tutor
          </div>
          <Link
            href="/teacher/dashboard"
            className="px-4 py-2 bg-cream-100 hover:bg-cream-200 text-ink-800 text-xs font-semibold rounded-xl transition-colors"
          >
            Tutor Dashboard
          </Link>
        </div>
      </div>

      {saveSuccessMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 p-4 rounded-2xl flex items-center gap-2 text-xs font-semibold animate-scale-up">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
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
            className="w-full pl-10 pr-4 py-2 bg-cream-50/50 border border-cream-200 rounded-xl text-xs sm:text-sm text-ink-900 focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
        </div>

        <div className="text-xs text-ink-500 font-medium">
          Total Regular Students: <strong className="text-ink-800">{students.length}</strong>
        </div>
      </div>

      {/* Student Dossier Cards */}
      <div className="grid grid-cols-1 gap-6">
        {filteredStudents.map((student) => (
          <div
            key={student.id}
            className="bg-white rounded-3xl border border-cream-200 shadow-sm overflow-hidden p-6 sm:p-8 space-y-6 hover:shadow-md transition-shadow"
          >
            {/* Header: Student Bio & Metas */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-cream-100 pb-5">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-2xl bg-teal-100/70 border border-teal-200 text-teal-800 flex items-center justify-center font-bold text-lg">
                  {student.student_name.slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-black text-ink-900">{student.student_name}</h3>
                    <span className="text-xs bg-teal-50 text-teal-800 border border-teal-200 font-bold px-2.5 py-0.5 rounded-full">
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
                  <span className="text-ink-400 block text-[10px] uppercase font-bold">Lessons Taken</span>
                  <strong className="text-ink-900 text-sm font-extrabold">{student.lessons_completed_count}</strong>
                </div>
                <div className="bg-cream-50 border border-cream-200 px-3.5 py-1.5 rounded-xl text-center">
                  <span className="text-ink-400 block text-[10px] uppercase font-bold">Last Lesson</span>
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
                    <FileText className="w-4 h-4 text-teal-600" />
                    <span>Private Pedagogical Notes</span>
                  </div>
                  {editingStudentId !== student.student_id ? (
                    <button
                      onClick={() => handleStartEdit(student)}
                      className="text-xs font-semibold text-teal-700 hover:text-teal-900 flex items-center gap-1"
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
                      className="w-full text-xs rounded-xl border border-cream-200 p-3 bg-cream-50/50 text-ink-900 focus:outline-none focus:ring-2 focus:ring-teal-500"
                    />
                    <div className="flex justify-end">
                      <button
                        onClick={() => handleSaveNotes(student.student_id)}
                        disabled={isSaving}
                        className="inline-flex items-center gap-1 px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-bold text-xs rounded-xl shadow-xs"
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
                  <AlertCircle className="w-4 h-4 text-amber-600" />
                  <span>Recurring Grammar & Pronunciation Slips</span>
                </div>

                <div className="bg-amber-50/30 border border-amber-200/60 rounded-2xl p-4 space-y-3 min-h-[96px]">
                  <div className="flex flex-wrap gap-1.5">
                    {student.common_grammar_mistakes.map((slip, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1 px-2.5 py-1 bg-white border border-amber-200 text-amber-900 rounded-lg text-xs font-medium shadow-2xs"
                      >
                        {slip}
                        <button
                          type="button"
                          onClick={() => handleRemoveMistake(student.student_id, idx)}
                          className="text-amber-400 hover:text-amber-800 ml-0.5"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>

                  <div className="flex items-center gap-2 pt-1 border-t border-amber-100">
                    <input
                      type="text"
                      value={draftMistake}
                      onChange={(e) => setDraftMistake(e.target.value)}
                      placeholder="Add recurring slip (e.g. 'Article omission')..."
                      className="flex-1 text-xs rounded-lg border border-cream-200 px-3 py-1.5 bg-white text-ink-900 focus:outline-none focus:ring-1 focus:ring-teal-500"
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
                      className="p-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs"
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
    </div>
  );
}
