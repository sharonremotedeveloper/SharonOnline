"use client";

import Link from "next/link";
import { useState } from "react";
import { BookOpen, Users, Compass, ShieldCheck, Menu, X } from "lucide-react";

export function Navbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-[#0D4440] text-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand Logo */}
        <Link href="/" className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-gold-500 flex items-center justify-center font-bold text-brand-950 text-lg">
            S
          </div>
          <span className="font-bold text-xl tracking-tight text-white">
            Sharon<span className="text-gold-500">Online</span>
          </span>
        </Link>

        {/* Desktop Navigation Links */}
        <nav className="hidden md:flex items-center space-x-8 text-sm font-medium text-white/90">
          <Link href="/tutors" className="hover:text-gold-500 transition-colors flex items-center gap-1.5">
            <Users className="w-4 h-4" /> Find Tutors
          </Link>
          <Link href="/materials" className="hover:text-gold-500 transition-colors flex items-center gap-1.5">
            <BookOpen className="w-4 h-4" /> Curriculum & Materials
          </Link>
          <Link href="/pricing" className="hover:text-gold-500 transition-colors flex items-center gap-1.5">
            <Compass className="w-4 h-4" /> Pricing & Packs
          </Link>
        </nav>

        {/* CTAs */}
        <div className="hidden md:flex items-center space-x-4">
          <Link
            href="/student/dashboard"
            className="text-sm font-semibold text-white/90 hover:text-white px-3 py-2"
          >
            Student Portal
          </Link>
          <Link
            href="/tutors"
            className="text-sm font-bold bg-gold-500 hover:bg-gold-600 text-brand-950 px-4 py-2 rounded-lg transition-all shadow-sm"
          >
            Book a Lesson
          </Link>
        </div>

        {/* Mobile Hamburger */}
        <div className="md:hidden flex items-center">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-md text-white/80 hover:text-white hover:bg-white/10"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden bg-[#0a3532] border-t border-white/10 px-4 pt-3 pb-6 space-y-3">
          <Link
            href="/tutors"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-500 text-base font-medium"
          >
            Find Tutors
          </Link>
          <Link
            href="/materials"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-500 text-base font-medium"
          >
            Curriculum & Materials
          </Link>
          <Link
            href="/pricing"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 text-white/90 hover:text-gold-500 text-base font-medium"
          >
            Pricing & Packs
          </Link>
          <div className="pt-2 border-t border-white/10 flex flex-col gap-2">
            <Link
              href="/student/dashboard"
              onClick={() => setMobileMenuOpen(false)}
              className="w-full text-center py-2 text-white/90 bg-white/10 rounded-lg text-sm font-semibold"
            >
              Student Portal
            </Link>
            <Link
              href="/tutors"
              onClick={() => setMobileMenuOpen(false)}
              className="w-full text-center py-2.5 text-brand-950 bg-gold-500 font-bold rounded-lg text-sm"
            >
              Book a Lesson
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
