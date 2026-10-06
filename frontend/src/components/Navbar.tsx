"use client";

import Link from "next/link";
import { useState } from "react";
import {
  BookOpen,
  Users,
  Compass,
  ShieldCheck,
  Briefcase,
  Menu,
  X,
  LogIn,
  LogOut,
  LayoutDashboard,
  Shield,
  Coins,
} from "lucide-react";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";
import { useAuth } from "@/context/AuthContext";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { NotificationBell } from "@/components/notifications";

export function Navbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { user, isAuthenticated, logout, role, isLoading, sessionError } = useAuth();

  const getDashboardLink = () => {
    if (role === "admin") return "/admin/dashboard";
    if (role === "teacher") return "/teacher/dashboard";
    return "/student/dashboard";
  };

  return (
    <header className="sticky top-0 z-50 bg-teal text-white shadow-md border-b border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand Logo */}
        <Link href="/" className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-xl bg-gold flex items-center justify-center font-bold text-teal text-lg shadow-sm font-serif">
            S
          </div>
          <span className="font-extrabold text-xl tracking-tight text-white font-serif">
            Sharon<span className="text-gold-bright">Online</span>
          </span>
        </Link>

        {/* Desktop Navigation Links */}
        <nav className="hidden lg:flex items-center space-x-6 text-xs font-bold text-white/90 uppercase tracking-wider">
          <Link href="/tutors" className="hover:text-gold-bright transition-colors flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5 text-accent" /> Find Tutors
          </Link>
          <Link href="/materials" className="hover:text-gold-bright transition-colors flex items-center gap-1.5">
            <BookOpen className="w-3.5 h-3.5 text-accent" /> Curriculum
          </Link>
          <Link href="/pricing" className="hover:text-gold-bright transition-colors flex items-center gap-1.5">
            <Compass className="w-3.5 h-3.5 text-accent" /> Pricing & Packs
          </Link>
          <Link href="/how-it-works" className="hover:text-gold-bright transition-colors flex items-center gap-1.5">
            How It Works
          </Link>
          <Link href="/trust-safety" className="hover:text-gold-bright transition-colors flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-accent" /> Trust & Safety
          </Link>
          <Link href="/teach" className="hover:text-gold-bright transition-colors flex items-center gap-1.5">
            <Briefcase className="w-3.5 h-3.5 text-accent" /> Teach
          </Link>
        </nav>

        {/* Desktop Right CTAs */}
        <div className="hidden lg:flex items-center space-x-3">
          <CurrencySwitcher variant="badge" />

          {isLoading ? (
            <div className="w-24 h-8 rounded-xl bg-white/10 animate-pulse" aria-label="Checking session" />
          ) : isAuthenticated && user ? (
            <div className="flex items-center space-x-3 pl-2 border-l border-white/20">
              {role === "student" && user.credits !== undefined && (
                <div className="flex items-center gap-1 px-2.5 py-1 bg-white/10 rounded-xl text-xs font-bold text-gold-bright border border-white/15">
                  <Coins className="w-3.5 h-3.5" />
                  <span>{user.credits} Credits</span>
                </div>
              )}

              <NotificationBell />

              <Link
                href={getDashboardLink()}
                className="flex items-center gap-2 hover:opacity-90 transition-opacity"
              >
                <Avatar
                  src={user.avatar_url}
                  name={`${user.first_name} ${user.last_name}`}
                  size="sm"
                />
                <div className="text-left">
                  <div className="text-xs font-bold text-white leading-tight">
                    {user.first_name || user.username}
                  </div>
                  <div className="text-[10px] text-accent capitalize">{role}</div>
                </div>
              </Link>

              <Link
                href={getDashboardLink()}
                className="px-3 py-1.5 rounded-xl bg-white/15 hover:bg-white/25 text-white text-xs font-bold flex items-center gap-1.5 transition-all"
              >
                <LayoutDashboard className="w-3.5 h-3.5" />
                <span>Dashboard</span>
              </Link>

              <button
                onClick={logout}
                title="Sign Out"
                className="p-1.5 rounded-xl text-white/70 hover:text-white hover:bg-white/10 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center space-x-2">
              {sessionError && (
                <span
                  title={sessionError}
                  className="text-[10px] font-bold text-gold-bright bg-white/10 border border-white/20 rounded-lg px-2 py-1"
                >
                  Session unavailable
                </span>
              )}
              <Link
                href="/login"
                className="text-xs font-bold text-white hover:text-gold-bright px-3 py-2 flex items-center gap-1"
              >
                <LogIn className="w-3.5 h-3.5" /> Sign In
              </Link>
              <Link
                href="/tutors"
                className="text-xs font-bold bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-xl transition-all shadow-sm"
              >
                Book Lesson
              </Link>
            </div>
          )}
        </div>

        {/* Mobile Hamburger */}
        <div className="lg:hidden flex items-center gap-2">
          {isAuthenticated && user && <NotificationBell />}
          <CurrencySwitcher variant="select" />
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-lg text-white/80 hover:text-white hover:bg-white/10"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="lg:hidden bg-teal-hover border-t border-white/10 px-4 pt-3 pb-6 space-y-3">
          {isAuthenticated && user && (
            <div className="p-3 bg-white/10 rounded-2xl flex items-center justify-between mb-2">
              <div className="flex items-center gap-2.5">
                <Avatar
                  src={user.avatar_url}
                  name={`${user.first_name} ${user.last_name}`}
                  size="sm"
                />
                <div>
                  <div className="text-xs font-bold text-white">{user.first_name} {user.last_name}</div>
                  <div className="text-[10px] text-accent capitalize">{role} workspace</div>
                </div>
              </div>
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                className="px-2.5 py-1 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs font-bold"
              >
                Sign Out
              </button>
            </div>
          )}

          <Link
            href="/tutors"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-bright text-sm font-bold"
          >
            Find Tutors
          </Link>
          <Link
            href="/materials"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-bright text-sm font-bold"
          >
            Curriculum & Materials
          </Link>
          <Link
            href="/pricing"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-bright text-sm font-bold"
          >
            Pricing & Packs
          </Link>
          <Link
            href="/how-it-works"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-bright text-sm font-bold"
          >
            How It Works
          </Link>
          <Link
            href="/trust-safety"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-bright text-sm font-bold"
          >
            Trust & Power Guard Safety
          </Link>
          <Link
            href="/teach"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-bright text-sm font-bold"
          >
            Teach With Us (South Africa)
          </Link>
          <Link
            href="/support"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-bright text-sm font-bold"
          >
            Support & FAQs
          </Link>

          <div className="pt-3 border-t border-white/10 flex flex-col gap-2">
            {isAuthenticated ? (
              <Link
                href={getDashboardLink()}
                onClick={() => setMobileMenuOpen(false)}
                className="w-full text-center py-2.5 text-white bg-primary font-bold rounded-xl text-xs"
              >
                Go to {role} Dashboard
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="w-full text-center py-2.5 text-white bg-white/10 rounded-xl text-xs font-bold"
                >
                  Sign In to Account
                </Link>
                <Link
                  href="/tutors"
                  onClick={() => setMobileMenuOpen(false)}
                  className="w-full text-center py-2.5 text-white bg-primary font-bold rounded-xl text-xs"
                >
                  Book a Lesson
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
