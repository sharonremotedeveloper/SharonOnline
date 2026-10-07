import React from "react";

export interface AvatarProps {
  src?: string;
  name?: string;
  alt?: string;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

export function Avatar({ src, name, alt, size = "md", className = "" }: AvatarProps) {
  const displayName = name || alt || "User";
  const sizeClasses = {
    sm: "w-8 h-8 text-xs",
    md: "w-10 h-10 text-sm",
    lg: "w-14 h-14 text-base",
    xl: "w-20 h-20 text-xl font-bold",
  }[size];

  const getInitials = (nameStr: string) => {
    return nameStr
      .split(" ")
      .map((part) => part[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  if (src) {
    return (
      <img
        src={src}
        alt={displayName}
        className={`${sizeClasses} rounded-full object-cover border border-divider ${className}`}
      />
    );
  }

  return (
    <div
      className={`${sizeClasses} rounded-full bg-cream-deep text-ink flex items-center justify-center font-medium border border-divider ${className}`}
      aria-label={displayName}
    >
      {getInitials(displayName)}
    </div>
  );
}
