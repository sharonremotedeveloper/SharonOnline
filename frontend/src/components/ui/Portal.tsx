"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Renders children into document.body. Required for dialogs and drawers: an ancestor with backdrop-filter,
 * transform or filter (the sticky header) becomes the containing block of `position: fixed` and would clip them.
 */
export function Portal({ children }: { children: ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  // Before mount (server render, first client render) the children render in place so markup matches; a dialog is closed then anyway.
  return mounted ? createPortal(children, document.body) : <>{children}</>;
}
