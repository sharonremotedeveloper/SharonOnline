"use client";

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

// Open dialogs, oldest first. Only the last one reacts to Escape and Tab, so a modal over a drawer closes alone.
const stack: symbol[] = [];

const isVisible = (el: HTMLElement) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";

/**
 * Dialog behaviour: focus moves in on open, Tab is trapped, Escape closes only the top dialog, and focus returns to the
 * opener on close. If the opener is gone or hidden (an account-menu row that closes as the drawer opens), focus goes to
 * the element marked `data-dialog-return` (the account button) instead of falling to <body>.
 */
export function useDialog(ref: RefObject<HTMLElement | null>, isOpen: boolean, onClose: () => void) {
  // The callback is read through a ref so a new function identity on every parent render never re-runs the effect
  // (which used to restore focus to the opener straight after moving it in).
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!isOpen) return;
    const id = Symbol("dialog");
    stack.push(id);
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const items = () => Array.from(ref.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(isVisible);

    // The dialog may be portalled and mount a frame after isOpen flips, so retry briefly until it exists.
    let tries = 0;
    let raf = 0;
    const focusIn = () => {
      if (!ref.current && tries++ < 20) {
        raf = requestAnimationFrame(focusIn);
        return;
      }
      if (stack[stack.length - 1] !== id) return;
      const first = items()[0];
      if (first) first.focus();
      else ref.current?.focus();
    };
    raf = requestAnimationFrame(focusIn);

    const onKey = (e: KeyboardEvent) => {
      if (stack[stack.length - 1] !== id) return;
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const list = items();
      if (list.length === 0) {
        e.preventDefault();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !ref.current?.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !ref.current?.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKey, true);
      const at = stack.indexOf(id);
      if (at >= 0) stack.splice(at, 1);
      const target =
        opener && opener.isConnected && isVisible(opener) ? opener : document.querySelector<HTMLElement>("[data-dialog-return]");
      // After the dialog unmounts, so the focus is not taken back by the closing animation or the trap.
      requestAnimationFrame(() => target?.focus());
    };
  }, [isOpen, ref]);
}
