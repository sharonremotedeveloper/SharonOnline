"use client";

import { useState } from "react";
import { HelpCircle, Mail, Send, CheckCircle2, MessageSquare } from "lucide-react";
import { submitInquiry } from "@/lib/api";
import { InlineError } from "@/components/ui/ErrorState";
import { ApiError } from "@/lib/http";

export default function SupportPage() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    subject: "",
    message: "",
    user_type: "student" as "student" | "teacher" | "other",
  });

  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [responseMsg, setResponseMsg] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setSubmitError(null);
    try {
      const res = await submitInquiry(formData);
      if (res.success) {
        setSubmitted(true);
        setResponseMsg(res.message);
        setFormData({ name: "", email: "", subject: "", message: "", user_type: "student" });
      } else {
        setSubmitError(res.message || "We couldn't send your message.");
      }
    } catch (err) {
      // Keep the typed text in the form so nothing is lost.
      const detail = err instanceof ApiError && err.status !== 404 && err.status !== 0 ? ` (${err.message})` : "";
      setSubmitError(
        `We couldn't send your message right now${detail}. Your text is still in the form - please try again later or contact us directly by email.`
      );
    } finally {
      setLoading(false);
    }
  };

  const faqs = [
    {
      q: "How do 25-minute lesson credits work?",
      a: "Each lesson ticket unlocks one 1-on-1 private 25-minute session with your chosen tutor. Lesson credits never expire.",
    },
    {
      q: "What happens if my tutor misses a class or loses power?",
      a: "Power Guard uses fresh provider evidence for student-reported tutor-area outages. Confirmed operational failures return one lesson credit to the wallet; tutor or staff reports remain subject to the lesson-time window.",
    },
    {
      q: "Which payment methods are accepted?",
      a: "We support PayFast (ZAR instant EFT and SA bank cards) as well as PayPal v2 (USD, EUR, JPY credit cards and balance).",
    },
    {
      q: "How do I cancel or reschedule a class?",
      a: "You can reschedule or cancel any lesson free of charge up to 2 hours before the start time directly from your student schedule.",
    },
  ];

  return (
    <div className="space-y-16 pb-16">
      {/* Header */}
      <section className="bg-cocoa text-white py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/20 text-xs font-bold text-accent-surface">
            <HelpCircle className="w-3.5 h-3.5 text-accent" />
            <span>24/7 Dedicated Platform Support</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold font-serif">Support & Frequently Asked Questions</h1>
          <p className="text-sm sm:text-base text-white/80 max-w-2xl mx-auto">
            Have questions about lesson booking, multi-currency credit packs, or South African tutor payouts? We're here to help.
          </p>
        </div>
      </section>

      {/* Grid: FAQs + Ticket Submission Form */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-2 gap-12">
        {/* FAQs */}
        <div className="space-y-6">
          <div className="space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Instant Answers</h2>
            <h3 className="text-2xl font-extrabold text-ink font-serif">Frequently Asked Questions</h3>
          </div>

          <div className="space-y-4">
            {faqs.map((faq, i) => (
              <details
                key={i}
                className="bg-white rounded-2xl p-6 border border-divider shadow-card group cursor-pointer"
              >
                <summary className="text-base font-bold text-ink flex items-center justify-between list-none">
                  <span>{faq.q}</span>
                  <span className="text-primary font-serif group-open:rotate-180 transition-transform">▼</span>
                </summary>
                <p className="text-xs text-ink-muted leading-relaxed mt-3 border-t border-divider pt-3">
                  {faq.a}
                </p>
              </details>
            ))}
          </div>
        </div>

        {/* Ticket Submission Form */}
        <div className="bg-white rounded-3xl p-8 border border-divider shadow-card space-y-6">
          <div className="space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Need Further Assistance?</h2>
            <h3 className="text-2xl font-extrabold text-ink font-serif">Submit a Support Inquiry</h3>
          </div>

          {submitted ? (
            <div className="bg-success/10 border border-success/30 rounded-2xl p-6 text-center space-y-3">
              <CheckCircle2 className="w-10 h-10 text-success mx-auto" />
              <div className="text-base font-bold text-ink">Inquiry Received</div>
              <p className="text-xs text-ink-muted leading-relaxed">{responseMsg}</p>
              <button
                onClick={() => setSubmitted(false)}
                className="px-4 py-2 bg-cocoa text-white rounded-xl text-xs font-bold"
              >
                Send Another Message
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-ink mb-1">I am a...</label>
                <div className="flex gap-4 text-xs font-semibold text-ink">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="user_type"
                      checked={formData.user_type === "student"}
                      onChange={() => setFormData({ ...formData, user_type: "student" })}
                      className="accent-cocoa"
                    />
                    Student
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="user_type"
                      checked={formData.user_type === "teacher"}
                      onChange={() => setFormData({ ...formData, user_type: "teacher" })}
                      className="accent-cocoa"
                    />
                    Tutor / Applicant
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-ink mb-1">Your Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Aiko Tanaka"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full bg-cream-surface border border-divider rounded-xl px-4 py-2.5 text-xs font-medium text-ink focus:outline-none focus:ring-2 focus:ring-cocoa"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-ink mb-1">Your Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="aiko@example.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full bg-cream-surface border border-divider rounded-xl px-4 py-2.5 text-xs font-medium text-ink focus:outline-none focus:ring-2 focus:ring-cocoa"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-ink mb-1">Subject</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Question about PayPal checkout or slot booking"
                  value={formData.subject}
                  onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                  className="w-full bg-cream-surface border border-divider rounded-xl px-4 py-2.5 text-xs font-medium text-ink focus:outline-none focus:ring-2 focus:ring-cocoa"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-ink mb-1">Message</label>
                <textarea
                  required
                  rows={4}
                  placeholder="How can we assist you today?"
                  value={formData.message}
                  onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                  className="w-full bg-cream-surface border border-divider rounded-xl px-4 py-2.5 text-xs font-medium text-ink focus:outline-none focus:ring-2 focus:ring-cocoa"
                />
              </div>

              <InlineError error={submitError} />

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50"
              >
                {loading ? "Submitting..." : <><Send className="w-4 h-4" /> Send Message</>}
              </button>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
