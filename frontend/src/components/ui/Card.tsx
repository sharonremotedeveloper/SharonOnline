import React, { type ReactNode } from "react";

export interface CardProps {
  children: ReactNode;
  accent?: "teal" | "gold" | "primary" | "plum" | "none";
  hoverEffect?: boolean;
  className?: string;
  onClick?: () => void;
}

export function Card({
  children,
  accent = "none",
  hoverEffect = false,
  className = "",
  onClick,
}: CardProps) {
  const accentBorder = {
    none: "",
    teal: "border-t-[3px] border-t-teal",
    gold: "border-t-[3px] border-t-gold",
    primary: "border-t-[3px] border-t-primary",
    plum: "border-t-[3px] border-t-plum",
  }[accent];

  const hoverStyle = hoverEffect
    ? "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover cursor-pointer"
    : "";

  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-lg p-5 border border-divider shadow-card ${accentBorder} ${hoverStyle} ${className}`}
    >
      {children}
    </div>
  );
}
