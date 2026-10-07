"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type ComponentType } from "react";
import {
  Bell,
  BookMarked,
  CalendarDays,
  ChevronDown,
  Coins,
  GraduationCap,
  Heart,
  History,
  LayoutDashboard,
  LogOut,
  UserRound,
  Users,
  Wallet,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Avatar } from "@/components/ui/Avatar";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";
import { NotificationDrawer, NotificationPreferencesModal } from "@/components/notifications";
import { useNotifications } from "@/hooks/useNotifications";
import { formatBadgeCount } from "@/lib/notifications";

type Icon = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" }>;
interface MenuLink {
  href: string;
  label: string;
  icon: Icon;
}

const STUDENT_LINKS: MenuLink[] = [
  { href: "/student/dashboard", label: "My dashboard", icon: LayoutDashboard },
  { href: "/student/schedule", label: "My lessons", icon: CalendarDays },
  { href: "/student/history", label: "Lesson history", icon: History },
  { href: "/student/vocabulary", label: "Flashcards", icon: BookMarked },
  { href: "/student/favorites", label: "Favourite tutors", icon: Heart },
  { href: "/student/wallet", label: "Wallet and receipts", icon: Wallet },
  { href: "/student/profile", label: "Profile and settings", icon: UserRound },
];

const TEACHER_LINKS: MenuLink[] = [
  { href: "/teacher/dashboard", label: "My dashboard", icon: LayoutDashboard },
  { href: "/teacher/schedule", label: "My hours", icon: CalendarDays },
  { href: "/teacher/students", label: "My students", icon: Users },
  { href: "/teacher/wallet", label: "Earnings and payouts", icon: Wallet },
  { href: "/teacher/training", label: "Training", icon: GraduationCap },
  { href: "/teacher/profile", label: "Profile and settings", icon: UserRound },
];

const ADMIN_LINKS: MenuLink[] = [{ href: "/admin/dashboard", label: "Admin dashboard", icon: LayoutDashboard }];

const FOCUSABLE = "a[href], button:not([disabled]), select:not([disabled])";

/**
 * The signed-in person in the header: one avatar button that opens a panel with their links, credits, notifications,
 * display currency and sign out. Replaces a row of five separate controls. It is a disclosure, not an ARIA menu:
 * the panel holds links, a select and buttons, so it uses aria-expanded and normal Tab order, plus arrow keys.
 */
export function AccountMenu() {
  const { user, role, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const notifs = useNotifications();
  const unread = formatBadgeCount(notifs.unreadCount);

  // Close on navigation.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Close on outside press and on Escape (focus returns to the button).
  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  const links = role === "admin" ? ADMIN_LINKS : role === "teacher" ? TEACHER_LINKS : STUDENT_LINKS;
  const fullName = `${user.first_name} ${user.last_name}`.trim() || user.username;
  const showCredits = role === "student" && user.credits !== undefined && user.credits !== null;

  // Arrow keys, Home and End move between the items in the panel.
  const onPanelKeyDown = (e: React.KeyboardEvent) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    const items = [...(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
    if (items.length === 0) return;
    const i = items.indexOf(document.activeElement as HTMLElement);
    let next = i;
    if (e.key === "ArrowDown") next = (i + 1) % items.length;
    if (e.key === "ArrowUp") next = (i - 1 + items.length) % items.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = items.length - 1;
    e.preventDefault();
    items[next]?.focus();
  };

  const rowClass =
    "flex min-h-[44px] w-full items-center gap-3 rounded-xl px-3 text-left text-base font-semibold text-ink transition-colors hover:bg-cream-surface focus-visible:bg-cream-surface";

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key !== "ArrowDown") return;
          e.preventDefault();
          setOpen(true);
          // The panel is mounted but hidden until the state flips: focus its first item once it shows.
          requestAnimationFrame(() => panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus());
        }}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`Account menu for ${fullName}${notifs.unreadCount > 0 ? `, ${notifs.unreadCount} unread notifications` : ""}`}
        className="relative flex min-h-[44px] items-center gap-1.5 rounded-full border border-divider bg-white py-1 pl-1 pr-2.5 text-ink shadow-sm transition-colors hover:bg-cream-surface"
      >
        <Avatar src={user.avatar_url} name={fullName} size="sm" />
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        {unread && (
          <span
            aria-hidden="true"
            className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-sun px-1 text-xs font-extrabold text-ink ring-2 ring-cream"
          >
            {unread}
          </span>
        )}
      </button>

      {/* Kept mounted and hidden when closed, so the currency control is ready the moment it opens */}
      <div
        hidden={!open}
        id={panelId}
        ref={panelRef}
        onKeyDown={onPanelKeyDown}
        className="fixed inset-x-3 top-[4.25rem] z-50 max-h-[calc(100dvh-5rem)] overflow-y-auto rounded-3xl border border-divider bg-white p-2 text-ink shadow-2xl sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[22rem]"
      >
        {/* Who */}
        <div className="flex items-center gap-3 px-3 pb-3 pt-2">
          <Avatar src={user.avatar_url} name={fullName} size="lg" />
          <div className="min-w-0">
            <p className="truncate font-serif text-lg font-bold leading-tight text-ink">{fullName}</p>
            <p className="truncate text-sm text-ink-muted">{user.email}</p>
            <p className="mt-1 inline-block rounded-full bg-sun-soft px-2.5 py-0.5 text-sm font-semibold capitalize text-ink">
              {role}
            </p>
          </div>
        </div>

        {/* Credits: the thing a student checks most */}
        {showCredits && (
          <Link
            href="/student/wallet"
            className="mx-1 mb-2 flex min-h-[56px] items-center justify-between gap-3 rounded-2xl bg-sun px-4 text-ink transition-colors hover:bg-sun-soft"
          >
            <span className="flex items-center gap-2.5">
              <Coins className="h-5 w-5" aria-hidden="true" />
              <span className="text-base font-bold">Lesson credits</span>
            </span>
            <span className="flex items-center gap-2">
              <span className="font-serif text-2xl font-extrabold leading-none">{user.credits}</span>
              <span className="text-sm font-bold underline underline-offset-2">Add</span>
            </span>
          </Link>
        )}

        {/* Where */}
        <nav aria-label="Account" className="border-t border-divider pt-1">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={pathname === href ? "page" : undefined}
              className={`${rowClass} ${pathname === href ? "bg-cream-surface" : ""}`}
            >
              <Icon className="h-5 w-5 shrink-0 text-ink-muted" aria-hidden={true} />
              {label}
            </Link>
          ))}
        </nav>

        {/* Notifications and currency */}
        <div className="mt-1 border-t border-divider pt-1">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              notifs.toggleOpen();
            }}
            className={rowClass}
          >
            <Bell className="h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
            <span className="flex-1">Notifications</span>
            {unread && (
              <span className="rounded-full bg-primary px-2.5 py-0.5 text-sm font-bold text-white">
                {unread}
                <span className="sr-only"> unread</span>
              </span>
            )}
          </button>
          <div className="flex min-h-[52px] items-center justify-between gap-3 px-3 py-1">
            <span className="text-base font-semibold text-ink">Show prices in</span>
            <CurrencySwitcher variant="select" />
          </div>
        </div>

        {/* Leave */}
        <div className="mt-1 border-t border-divider pt-1">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
            className={`${rowClass} text-error hover:bg-error-surface`}
          >
            <LogOut className="h-5 w-5 shrink-0" aria-hidden="true" />
            Sign out
          </button>
        </div>
      </div>

      {/* The notification list and its settings still open as before, from the menu row */}
      <NotificationDrawer
        isOpen={notifs.isOpen}
        onClose={notifs.close}
        notifications={notifs.notifications}
        unreadCount={notifs.unreadCount}
        isLoading={notifs.isLoading}
        isLoadingMore={notifs.isLoadingMore}
        hasMore={notifs.hasMore}
        onFetchMore={notifs.fetchMore}
        onMarkRead={notifs.markRead}
        onMarkAllRead={notifs.markAllRead}
        onOpenPreferences={notifs.togglePreferences}
      />
      <NotificationPreferencesModal
        isOpen={notifs.preferencesOpen}
        onClose={notifs.closePreferences}
        preferences={notifs.preferences}
        onSave={notifs.savePreferences}
        isSaving={notifs.isSavingPreferences}
      />
    </div>
  );
}
