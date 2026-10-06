"use client";

import { useState } from "react";
import { MaterialDetail } from "@/types/material";
import { SplitScreenReader } from "@/components/materials/SplitScreenReader";
import { Maximize2, Minimize2, BookOpen, Video, Columns } from "lucide-react";

interface ClassroomSplitLayoutProps {
  material: MaterialDetail | null;
  children: React.ReactNode; // Staging / Video Stage Content
  isTeacher?: boolean;
}

export function ClassroomSplitLayout({
  material,
  children,
  isTeacher = false,
}: ClassroomSplitLayoutProps) {
  const [viewMode, setViewMode] = useState<"split" | "video_focus" | "material_focus">("split");

  return (
    <div className="space-y-4">
      {/* Layout Control Bar */}
      <div className="flex items-center justify-between bg-white px-5 py-2.5 rounded-2xl border border-divider shadow-sm">
        <span className="text-xs font-bold text-ink-muted flex items-center gap-2">
          <Columns className="w-4 h-4 text-cocoa" />
          <span>Classroom Dual-Pane Stage</span>
        </span>

        <div className="flex items-center gap-1 bg-cream-surface rounded-xl p-1 border border-divider">
          <button
            type="button"
            onClick={() => setViewMode("split")}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              viewMode === "split"
                ? "bg-white text-cocoa shadow-xs border border-divider"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            <Columns className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">50/50 Split</span>
          </button>

          <button
            type="button"
            onClick={() => setViewMode("video_focus")}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              viewMode === "video_focus"
                ? "bg-white text-cocoa shadow-xs border border-divider"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            <Video className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Video Stage Only</span>
          </button>

          {material && (
            <button
              type="button"
              onClick={() => setViewMode("material_focus")}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                viewMode === "material_focus"
                  ? "bg-white text-cocoa shadow-xs border border-divider"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Material Only</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Dual Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Left Pane: Zoom Video & Staging Cockpit */}
        <div
          className={`${
            viewMode === "video_focus"
              ? "lg:col-span-12"
              : viewMode === "material_focus"
              ? "hidden"
              : material
              ? "lg:col-span-6"
              : "lg:col-span-12"
          } space-y-6 flex flex-col justify-start`}
        >
          {children}
        </div>

        {/* Right Pane: Embedded Synchronized Material Reader */}
        {material && (
          <div
            className={`${
              viewMode === "material_focus"
                ? "lg:col-span-12"
                : viewMode === "video_focus"
                ? "hidden"
                : "lg:col-span-6"
            } min-h-[500px] lg:min-h-[680px] flex flex-col`}
          >
            <SplitScreenReader material={material} className="flex-1 h-full shadow-card" />
          </div>
        )}
      </div>
    </div>
  );
}
