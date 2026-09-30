"use client";

import { Globe } from "lucide-react";

interface TimezoneSelectorProps {
  value: string;
  onChange: (tz: string) => void;
  className?: string;
}

export const TIMEZONE_OPTIONS = [
  { value: "Asia/Tokyo", label: "Tokyo, Japan (JST, UTC+9)", flag: "🇯🇵" },
  { value: "Asia/Seoul", label: "Seoul, South Korea (KST, UTC+9)", flag: "🇰🇷" },
  { value: "Europe/London", label: "London, UK (GMT/BST, UTC+0/+1)", flag: "🇬🇧" },
  { value: "Europe/Paris", label: "Paris / Berlin (CET/CEST, UTC+1/+2)", flag: "🇪🇺" },
  { value: "Africa/Johannesburg", label: "Johannesburg, SA (SAST, UTC+2)", flag: "🇿🇦" },
  { value: "America/New_York", label: "New York, USA (EST/EDT, UTC-5/-4)", flag: "🇺🇸" },
  { value: "America/Los_Angeles", label: "Los Angeles, USA (PST/PDT, UTC-8/-7)", flag: "🇺🇸" },
];

export function TimezoneSelector({ value, onChange, className = "" }: TimezoneSelectorProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <Globe className="w-4 h-4 text-teal shrink-0" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-cream-surface border border-divider rounded-xl px-3 py-1.5 text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal cursor-pointer"
      >
        {TIMEZONE_OPTIONS.map((tz) => (
          <option key={tz.value} value={tz.value}>
            {tz.flag} {tz.label}
          </option>
        ))}
      </select>
    </div>
  );
}
