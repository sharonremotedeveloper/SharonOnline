import { API_BASE, MOCK, USE_MOCKS, liveRequest, request } from "./http";
import type { components } from "@/types/api.generated";
import { BookingDetail, BookingSlot, CreditLedgerEntry } from "@/types/booking";
import {
  EskomStatus,
  PowerBackupInput,
  PostLessonMemoInput,
  TeacherPayoutBankAccount,
  TeacherWalletData,
  TeacherPayoutBankAccountInput,
} from "@/types/teacher";
import {
  AdminTelemetry,
  PendingTeacherApplication,
  LiveSessionRadarItem,
  DisputeCase,
  FinanceEscrowItem,
  PayoutBatchItem,
} from "@/types/admin";
import {
  StudentLessonItem,
  StudentFlashcard,
  StudentProfileData,
  TeacherStudentDossierItem,
} from "@/types/student";

export interface FeaturedTeacher {
  id: string;
  slug: string;
  name: string;
  avatar: string;
  video_url: string;
  accent: string;
  rating: number;
  review_count: number;
  hourly_rate: number;
  bio: string;
  specialties: string[];
}

export interface InquiryPayload {
  name: string;
  email: string;
  subject: string;
  message: string;
  user_type?: "student" | "teacher" | "other";
}

export async function fetchFeaturedTutors(): Promise<FeaturedTeacher[]> {
  // Server component: never throw (a marketing page must still render) and never invent tutors.
  // The backend has no "featured" flag yet, so take the first few verified tutors it returns.
  try {
    const data = await request(`${API_BASE}/teachers/?page_size=3`, { next: { revalidate: 60 } } as RequestInit);
    const rawList: any[] = Array.isArray(data) ? data : data?.results || [];
    return rawList.slice(0, 3).map((t) => ({
      id: String(t.id),
      slug: String(t.slug || t.id),
      name: String(t.full_name || t.first_name || ""),
      avatar: t.avatar_url || "",
      video_url: t.intro_video_url || "",
      accent: t.accent || "",
      rating: Number(t.rating_avg ?? 0),
      review_count: Number(t.rating_count ?? 0),
      hourly_rate: Number(t.price_per_25min_usd ?? 0),
      bio: t.headline || t.bio || "",
      specialties: Array.isArray(t.specialties) ? t.specialties : [],
    }));
  } catch (err) {
    if (USE_MOCKS) return FALLBACK_TUTORS;
    console.error("Could not load featured tutors:", err);
    return [];
  }
}

export async function submitInquiry(payload: InquiryPayload): Promise<{ success: boolean; message: string }> {
  // Throws ApiError on failure so the form can tell the user their message did NOT go through.
  const live = await liveRequest(`${API_BASE}/auth/inquiries/`, { method: "POST", body: JSON.stringify(payload) });
  if (live !== MOCK) {
    return { success: true, message: "Thanks - your message was sent. Our support team will reply by email." };
  }
  return { success: true, message: "Thank you! Your ticket has been received. (mock mode)" };
}

/**
 * Django serialises DecimalFields (rating_avg, price_per_25min_usd) as STRINGS ("4.50"). Coerce them once here so no
 * page has to remember to call Number() before .toFixed().
 */
function normalizeTutor<T>(t: T): T {
  if (!t || typeof t !== "object") return t;
  const raw = t as Record<string, unknown>;
  return {
    ...raw,
    ...(raw.rating_avg !== undefined && { rating_avg: Number(raw.rating_avg) || 0 }),
    ...(raw.rating_count !== undefined && { rating_count: Number(raw.rating_count) || 0 }),
    ...(raw.price_per_25min_usd !== undefined && { price_per_25min_usd: Number(raw.price_per_25min_usd) || 0 }),
  } as T;
}

function normalizeBooking(raw: components["schemas"]["BookingDetail"]): BookingDetail {
  const { rating_avg, price_per_25min_usd, ...teacher } = raw.teacher;
  return {
    ...raw,
    teacher: {
      ...teacher,
      ...(rating_avg !== undefined && { rating_avg: Number(rating_avg) || 0 }),
      ...(price_per_25min_usd !== undefined && {
        price_per_25min_usd: Number(price_per_25min_usd) || 0,
      }),
    },
  };
}

function normalizeTutorList(data: any) {
  if (Array.isArray(data)) return data.map(normalizeTutor);
  if (data && Array.isArray(data.results)) return { ...data, results: data.results.map(normalizeTutor) };
  return data;
}

const FALLBACK_TUTORS: FeaturedTeacher[] = [
  {
    id: "tut-1",
    slug: "sharon-m",
    name: "Sharon M.",
    avatar: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
    video_url: "https://assets.mixkit.co/videos/preview/mixkit-woman-talking-on-video-call-41292-large.mp4",
    accent: "South African (Neutral)",
    rating: 4.98,
    review_count: 142,
    hourly_rate: 8.0,
    bio: "10+ years teaching business English to Japanese & Korean executives. Friendly, patient, focused on natural pronunciation.",
    specialties: ["Business English", "Interview Prep", "FreeTalk"],
  },
  {
    id: "tut-2",
    slug: "david-k",
    name: "David K.",
    avatar: "https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=400&q=80",
    video_url: "https://assets.mixkit.co/videos/preview/mixkit-man-having-a-video-call-on-a-laptop-41288-large.mp4",
    accent: "South African (RP Accent)",
    rating: 4.95,
    review_count: 98,
    hourly_rate: 8.0,
    bio: "TEFL certified tutor specializing in IELTS speaking exam preparation and advanced vocabulary acquisition.",
    specialties: ["IELTS Prep", "Grammar Mastery", "Daily News"],
  },
  {
    id: "tut-3",
    slug: "elena-v",
    name: "Elena V.",
    avatar: "https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=400&q=80",
    video_url: "https://assets.mixkit.co/videos/preview/mixkit-young-woman-in-online-meeting-41290-large.mp4",
    accent: "British / SA Neutral",
    rating: 4.92,
    review_count: 86,
    hourly_rate: 8.0,
    bio: "Passionate about building speaking confidence for beginners and intermediate English learners.",
    specialties: ["Beginner A1-B1", "Conversation", "Travel English"],
  },
];

import { MaterialDetail } from "@/types/material";

export const FALLBACK_MATERIALS: MaterialDetail[] = [
  {
    id: "mat-1",
    slug: "remote-work-trends",
    title: "Global Remote Work & Digital Nomads",
    category: "daily_news",
    category_display: "Daily News & Discussion",
    cefr_level: "B2",
    cefr_display: "B2 Upper-Intermediate",
    estimated_minutes: 25,
    summary: "Explore emerging workplace trends, the shift to asynchronous communication, and how cross-border teams collaborate across time zones.",
    content_html: `
      <p>Over the past five years, the global employment landscape has undergone a seismic paradigm shift. What began as an emergency measure during the pandemic has evolved into an entrenched workforce preference: <strong>remote and distributed work</strong>.</p>
      <p>Companies headquartered in financial hubs such as Tokyo, London, and New York are increasingly hiring talent irrespective of geographical borders. However, leading cross-cultural teams requires transitioning away from real-time meetings toward <span class="vocab-highlight font-bold text-teal underline" data-vocab="Asynchronous">asynchronous</span> workflows where documentation takes precedence over spontaneous office banter.</p>
      <p>Advocates argue that asynchronous rhythms boost deep focus and overall <span class="vocab-highlight font-bold text-teal underline" data-vocab="Productivity">productivity</span>, freeing knowledge workers from constant message pings. Conversely, skeptics caution against the risk of employee alienation and reduced spontaneous innovation.</p>
      <p>As multinational enterprises strive for the optimal <span class="vocab-highlight font-bold text-teal underline" data-vocab="Equilibrium">equilibrium</span> between in-office cohesion and flexible autonomy, digital nomad visas in countries like Spain, Japan, and South Africa have surged in popularity, signaling that location independence is here to stay.</p>
    `,
    vocabulary: [
      {
        id: "v-1",
        word: "Asynchronous",
        phonetic: "/eɪˈsɪŋ.krə.nəs/",
        part_of_speech: "adjective",
        definition: "Communication or operations not occurring simultaneously or in real time.",
        example_sentence: "Asynchronous updates via shared documents prevent unnecessary late-night video conferences."
      },
      {
        id: "v-2",
        word: "Productivity",
        phonetic: "/ˌprɒd.ʌkˈtɪv.ə.ti/",
        part_of_speech: "noun",
        definition: "The effectiveness of productive effort, especially in terms of output per unit of input.",
        example_sentence: "Clear project milestones allow managers to evaluate productivity without micromanaging hours."
      },
      {
        id: "v-3",
        word: "Equilibrium",
        phonetic: "/ˌiː.kwɪˈlɪb.ri.əm/",
        part_of_speech: "noun",
        definition: "A state in which opposing forces or influences are balanced.",
        example_sentence: "Achieving a sustainable work-life equilibrium is crucial when your living room is also your office."
      }
    ],
    discussion_questions: [
      "Do you personally prefer remote work, hybrid scheduling, or full-time office environments? Why?",
      "What communication hurdles arise when collaborating with colleagues across 8+ hour timezone differentials?",
      "How can managers assess trust and deliverables without tracking keystrokes or camera time?",
      "Would you consider becoming a digital nomad if your company offered complete location independence?"
    ],
    pdf_file_url: "https://pub-088f123.r2.dev/worksheets/remote-work-trends.pdf",
    downloads_count: 342,
    created_at: "2026-09-15T10:00:00Z"
  },
  {
    id: "mat-2",
    slug: "cross-cultural-negotiation",
    title: "Mastering Cross-Cultural Business Negotiations",
    category: "business",
    category_display: "Business & Workplace",
    cefr_level: "C1",
    cefr_display: "C1 Advanced",
    estimated_minutes: 25,
    summary: "Discover how high-context versus low-context communication styles influence deal-making, conflict resolution, and executive decision-making.",
    content_html: `
      <p>Entering international commercial negotiations without a nuanced appreciation of cultural context is a recipe for diplomatic stalemate. Anthropologist Edward T. Hall famously categorized communication cultures into <em>high-context</em> and <em>low-context</em> paradigms.</p>
      <p>In low-context environments—common in Germany, the United States, and the Netherlands—messages are explicit, direct, and literal. Contracts are expected to account for every conceivable contingency. In contrast, in high-context cultures such as Japan, South Korea, and Saudi Arabia, meaning is heavily embedded within situational cues, non-verbal gestures, and long-standing interpersonal trust.</p>
      <p>A seasoned executive must exercise acute <span class="vocab-highlight font-bold text-teal underline" data-vocab="Diplomatic">diplomatic</span> tact, recognizing that an abrupt rejection or rigid ultimatum can permanently sever relationships. Strategic <span class="vocab-highlight font-bold text-teal underline" data-vocab="Concession">concessions</span> should be framed collaboratively to ensure all parties preserve face and foster enduring enterprise partnerships.</p>
    `,
    vocabulary: [
      {
        id: "v-4",
        word: "Diplomatic",
        phonetic: "/ˌdɪp.ləˈmæt.ɪk/",
        part_of_speech: "adjective",
        definition: "Showing skill in handling difficult people or situations peacefully and tactfully.",
        example_sentence: "Her diplomatic intervention defused tension between the overseas joint-venture partners."
      },
      {
        id: "v-5",
        word: "Concession",
        phonetic: "/kənˈseʃ.ən/",
        part_of_speech: "noun",
        definition: "A thing that is granted or yielded, especially in response to demands during negotiations.",
        example_sentence: "Both sides agreed to a minor pricing concession to expedite contract execution."
      }
    ],
    discussion_questions: [
      "In your home culture, is it customary to get straight to business, or is relationship-building preferred first?",
      "How do you communicate disagreement with senior stakeholders in a polite, culturally sensitive manner?",
      "Can a rigid legal contract compensate for a lack of personal trust between international partners?"
    ],
    pdf_file_url: "https://pub-088f123.r2.dev/worksheets/cross-cultural-negotiation.pdf",
    downloads_count: 512,
    created_at: "2026-09-18T14:30:00Z"
  },
  {
    id: "mat-3",
    slug: "travel-hidden-gems",
    title: "Travel Anecdotes & Hidden Cultural Gems",
    category: "freetalk",
    category_display: "FreeTalk Prompts",
    cefr_level: "B1",
    cefr_display: "B1 Intermediate",
    estimated_minutes: 25,
    summary: "Share memorable travel experiences, exploring off-the-beaten-path destinations, and adapting to unexpected itineraries.",
    content_html: `
      <p>Travel is often celebrated for picturesque postcards and famous monuments, but the most unforgettable journeys frequently emerge from unforeseen detours.</p>
      <p>Whether it is getting stranded at a rural train platform in Hokkaido or stumbling upon a family-run trattoria in Florence that is not listed in any guidebook, spontaneous discoveries leave the deepest impression. Escaping the tourist crowds requires an appetite for <span class="vocab-highlight font-bold text-teal underline" data-vocab="Serendipity">serendipity</span> and a willingness to converse with local residents.</p>
      <p>Travelers who venture off the beaten path frequently develop greater adaptability and cultural empathy, turning minor travel mishaps into lifetime stories.</p>
    `,
    vocabulary: [
      {
        id: "v-6",
        word: "Serendipity",
        phonetic: "/ˌser.ənˈdɪp.ə.ti/",
        part_of_speech: "noun",
        definition: "The occurrence and development of events by chance in a happy or beneficial way.",
        example_sentence: "Finding the rooftop cafe during a sudden thunderstorm was pure serendipity."
      }
    ],
    discussion_questions: [
      "Describe the most memorable meal or dish you have ever eaten while traveling.",
      "Have you ever experienced a travel delay or luggage mishap that turned into a funny adventure?",
      "Do you meticulously plan every hour of your vacation, or do you prefer spontaneous exploring?"
    ],
    pdf_file_url: "https://pub-088f123.r2.dev/worksheets/travel-hidden-gems.pdf",
    downloads_count: 420,
    created_at: "2026-09-20T09:15:00Z"
  },
  {
    id: "mat-4",
    slug: "behavioral-job-interview",
    title: "Acing the Behavioral Job Interview with STAR",
    category: "test_prep",
    category_display: "Job Interview & Test Prep",
    cefr_level: "B2",
    cefr_display: "B2 Upper-Intermediate",
    estimated_minutes: 25,
    summary: "Master the Situation, Task, Action, Result framework to narrate compelling leadership and problem-solving anecdotes in English.",
    content_html: `
      <p>Global tech firms and international organizations rely heavily on behavioral interviewing to assess candidates. Rather than asking hypothetical questions, hiring panels probe for concrete historical evidence: <em>'Tell me about a time you managed a project deadline crisis.'</em></p>
      <p>The definitive technique for answering behavioral prompts is the <strong>STAR method</strong> (Situation, Task, Action, Result). Candidates should spend approximately 70% of their response elucidating the specific <strong>Actions</strong> they personally initiated and the measurable <strong>Results</strong> achieved.</p>
      <p>Articulating complex technical achievements in clear, concise English requires active verbs and quantifiable metrics, demonstrating both functional competency and executive composure.</p>
    `,
    vocabulary: [
      {
        id: "v-7",
        word: "Quantifiable",
        phonetic: "/ˈkwɒn.tɪ.faɪ.ə.bəl/",
        part_of_speech: "adjective",
        definition: "Able to be expressed or measured as a quantity or number.",
        example_sentence: "Highlight quantifiable results on your resume, such as reducing latency by 40%."
      }
    ],
    discussion_questions: [
      "How do you prepare for interviews when English is not your native language?",
      "Think of a challenging conflict with a teammate. How would you explain your resolution using STAR?",
      "What are the most impactful questions a candidate can ask an interviewer at the end of a session?"
    ],
    pdf_file_url: "https://pub-088f123.r2.dev/worksheets/behavioral-job-interview.pdf",
    downloads_count: 678,
    created_at: "2026-09-22T11:45:00Z"
  },
  {
    id: "mat-5",
    slug: "everyday-introductions",
    title: "First Impressions & Self-Introductions",
    category: "freetalk",
    category_display: "FreeTalk Prompts",
    cefr_level: "A1",
    cefr_display: "A1 Beginner",
    estimated_minutes: 20,
    summary: "Essential expressions to introduce yourself, state your profession, and describe your hometown with ease and warmth.",
    content_html: `
      <p>Making a good first impression in English starts with confident, natural introductions. Whether meeting a new tutor, an exchange student, or an international coworker, clear pronunciation and friendly body language make all the difference.</p>
      <p>Start with simple, welcoming sentences: <em>'Hello, my name is Alex. It is a pleasure to meet you.'</em> Share where you live, what you do, and what you enjoy doing in your free time.</p>
    `,
    vocabulary: [
      {
        id: "v-8",
        word: "Pleasure",
        phonetic: "/ˈpleʒ.ər/",
        part_of_speech: "noun",
        definition: "A feeling of happy satisfaction and enjoyment.",
        example_sentence: "It is a pleasure to meet you today."
      }
    ],
    discussion_questions: [
      "Where are you from, and what is your hometown famous for?",
      "What do you enjoy doing on the weekends?",
      "Why are you studying English right now?"
    ],
    pdf_file_url: "https://pub-088f123.r2.dev/worksheets/everyday-introductions.pdf",
    downloads_count: 819,
    created_at: "2026-09-25T08:00:00Z"
  },
  {
    id: "mat-6",
    slug: "executive-presence-nuance",
    title: "Nuance and Diplomatic Phrasing for Executives",
    category: "business",
    category_display: "Business & Workplace",
    cefr_level: "C2",
    cefr_display: "C2 Proficient",
    estimated_minutes: 25,
    summary: "Refine executive tone, master hedging, and handle contentious boardroom discourse with poise and precision.",
    content_html: `
      <p>At the C-suite tier, communication prowess is defined less by vocabulary breadth and more by the deliberate modulation of tone, hedging, and subtle diplomacy.</p>
      <p>Direct assertiveness can often be misconstrued as aggressive or unsophisticated in high-stakes multinational forums. Mastering indirect phrasing, conditioned assertions, and open-ended reframing allows senior directors to steer controversial agendas without provoking defensive entrenchment from key stakeholders.</p>
    `,
    vocabulary: [
      {
        id: "v-9",
        word: "Hedging",
        phonetic: "/ˈhedʒ.ɪŋ/",
        part_of_speech: "noun",
        definition: "The use of cautious or ambiguous language to soften statements or avoid absolute commitments.",
        example_sentence: "Strategic hedging like 'It might be prudent to consider' allows executives to propose ideas diplomatically."
      }
    ],
    discussion_questions: [
      "How do leaders maintain authority while remaining approachable and empathetic?",
      "In boardroom settings, how do you challenge a prevailing consensus without appearing obstructive?",
      "What distinguishes a great bilingual corporate communicator from an average one?"
    ],
    pdf_file_url: "https://pub-088f123.r2.dev/worksheets/executive-presence-nuance.pdf",
    downloads_count: 290,
    created_at: "2026-09-26T16:00:00Z"
  }
];

export const api = {
  async getTutors(params?: any) {
    const query = params ? `?${new URLSearchParams(params).toString()}` : "";
    const live = await liveRequest(`${API_BASE}/teachers/${query}`, {});
    if (live !== MOCK) return normalizeTutorList(live);
    return { results: FALLBACK_TUTORS, count: FALLBACK_TUTORS.length };
  },

  async getTeachers(params?: any) {
    return this.getTutors(params);
  },

  async getTutor(id: string) {
    const live = await liveRequest(`${API_BASE}/teachers/${id}/`, {});
    if (live !== MOCK) return normalizeTutor(live);
    return FALLBACK_TUTORS.find((t) => t.id === id || t.slug === id) || FALLBACK_TUTORS[0];
  },

  async getTeacher(id: string) {
    return this.getTutor(id);
  },

  async getTeacherSlots(id: string, timezone?: string, days = 14) {
    const live = await liveRequest(`${API_BASE}/bookings/slots/${id}/?tz=${encodeURIComponent(timezone || "Asia/Tokyo")}&days=${days}`, {});
    if (live !== MOCK) return live;

    // Fallback generator for 14 rolling days
    const today = new Date();
    const slots: BookingSlot[] = [];

    const timePresets = [
      { start: "09:00", end: "09:25", hour: 9 },
      { start: "10:00", end: "10:25", hour: 10 },
      { start: "14:00", end: "14:25", hour: 14 },
      { start: "17:30", end: "17:55", hour: 17 },
      { start: "19:00", end: "19:25", hour: 19 },
      { start: "20:30", end: "20:55", hour: 20 },
    ];

    for (let d = 0; d < days; d++) {
      const current = new Date(today);
      current.setDate(today.getDate() + d);
      const dateStr = current.toISOString().split("T")[0];

      timePresets.forEach((p, idx) => {
        const isAvailable = (d + idx) % 5 !== 0; // varied availability simulation
        slots.push({
          id: `slot-${id}-${dateStr}-${p.start.replace(":", "")}`,
          start_time_utc: `${dateStr}T${(p.hour - 7).toString().padStart(2, "0")}:00:00Z`,
          end_time_utc: `${dateStr}T${(p.hour - 7).toString().padStart(2, "0")}:25:00Z`,
          local_date: dateStr,
          local_start_time: p.start,
          local_end_time: p.end,
          viewer_timezone: timezone || "Asia/Tokyo",
          status: isAvailable ? "available" : "booked",
          is_bookable: isAvailable,
        });
      });
    }

    return {
      teacher_id: id,
      teacher_name: "Sharon M.",
      viewer_timezone: timezone || "Asia/Tokyo",
      slot_count: slots.length,
      slots,
    };
  },

  async reserveSlot(teacherId: string, startTimeUtc: string) {
    const live = await liveRequest(`${API_BASE}/bookings/reserve/`, {
        method: "POST",
        body: JSON.stringify({
          teacher_id: teacherId,
          start_time_utc: startTimeUtc,
        }),
      });
    if (live !== MOCK) return live;

    const generatedId = `BK-${Date.now().toString().slice(-6)}`;
    return {
      booking_id: generatedId,
      lock_ttl_seconds: 600,
      status: "pending_payment" as const,
      expires_at: new Date(Date.now() + 600000).toISOString(),
    };
  },

  async getBooking(bookingId: string): Promise<BookingDetail> {
    const live = await liveRequest(`${API_BASE}/bookings/${bookingId}/`, {});
    if (live !== MOCK) return normalizeBooking(live as components["schemas"]["BookingDetail"]);

    // Fallback booking object for seamless testing
    const today = new Date();
    return {
      id: bookingId,
      booking_reference: bookingId.startsWith("BK-") ? bookingId : `BK-${bookingId.slice(0, 6)}`,
      teacher: {
        id: "tut-1",
        user_id: "usr-teacher-01",
        full_name: "Sharon M.",
        first_name: "Sharon",
        last_name: "M.",
        avatar_url: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
        intro_audio_url: "",
        country: "ZA",
        accent: "ZA",
        price_per_25min_usd: 8.0,
      },
      student: {
        id: "usr-student-01",
        full_name: "Aiko Tanaka",
        first_name: "Aiko",
        email: "aiko@example.com",
        country: "JP",
        timezone: "Asia/Tokyo",
        target_level: "",
        learning_goals: "",
      },
      material: null,
      start_time_utc: today.toISOString(),
      end_time_utc: new Date(today.getTime() + 25 * 60000).toISOString(),
      local_date: today.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }),
      local_start_time: "17:30",
      local_end_time: "17:55",
      viewer_timezone: "Asia/Tokyo (JST)",
      status: "confirmed",
      price_usd: 8.0,
      price_zar: 150.0,
      lock_expires_at: new Date(Date.now() + 540000).toISOString(),
      zoom_url: "https://zoom.us/j/9876543210?pwd=ESL_CLASS_ROOM",
      zoom_password: "SHARON_ONLINE",
      zoom_meeting_id: "987 654 3210",
      zoom_join_url: "https://zoom.us/j/9876543210?pwd=ESL_CLASS_ROOM",
      zoom_start_url: "https://zoom.us/s/9876543210?zak=ESL_TEACHER_HOST_TOKEN",
      material_slug: "remote-work-trends",
      material_title: "Global Remote Work & Digital Nomads",
      student_rating: null,
      memo: null,
      created_at: new Date().toISOString(),
    };
  },

  async reportPowerOutage(bookingId: string, reason?: string) {
    const live = await liveRequest(`${API_BASE}/bookings/${bookingId}/report-outage/`, {
        method: "POST",
        body: JSON.stringify({ reason: reason || "Eskom Load Shedding / Power Interruption" }),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      booking_id: bookingId,
      status: "interrupted_power" as const,
      message: "Eskom load shedding reported. Student credit refunded and tutor rating protected.",
      refund_issued: true,
    };
  },

  async redeemCredit(bookingId: string) {
    const live = await liveRequest(`${API_BASE}/bookings/${bookingId}/redeem-credit/`, {
        method: "POST",
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      booking_id: bookingId,
      status: "confirmed",
      message: "1 Lesson Credit redeemed successfully.",
    };
  },

  async initializeCheckout(payload: {
    gateway: "payfast" | "paypal";
    booking_id?: string;
    credit_pack_id?: number;
    currency?: "USD" | "ZAR" | "EUR" | "JPY";
  }) {
    const live = await liveRequest(`${API_BASE}/payments/checkout/init/`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    if (live !== MOCK) return live;
    throw new Error("Checkout initialization is unavailable in mock mode.");
  },

  async getCreditPacks() {
    const live = await liveRequest(`${API_BASE}/payments/credit-packs/`, { skipAuth: true });
    if (live !== MOCK) return live;
    return [];
  },

  async getCreditPurchase(purchaseId: string) {
    const live = await liveRequest(`${API_BASE}/payments/credit-purchases/${purchaseId}/`, {});
    if (live !== MOCK) return live;
    throw new Error("Credit purchase status is unavailable in mock mode.");
  },

  async getStudentWallet() {
    const live = await liveRequest(`${API_BASE}/payments/credits/`, {});
    if (live !== MOCK) return live;

    const defaultLedger: CreditLedgerEntry[] = [
      {
        id: "led-1",
        description: "Starter Pack Purchase (5 Lessons)",
        credits_delta: +5,
        date: "2026-09-20",
        type: "purchase",
      },
      {
        id: "led-2",
        description: "Lesson Redeemed with Sharon M.",
        credits_delta: -1,
        date: "2026-09-24",
        type: "redemption",
      },
      {
        id: "led-3",
        description: "Welcome Bonus Credit",
        credits_delta: +1,
        date: "2026-09-18",
        type: "bonus",
      },
    ];

    return {
      total_credits: 5,
      ledger: defaultLedger,
      bundles: [{ pack_name: "5-Lesson Pack", remaining: 5, total: 5, purchased_at: "2026-09-20T00:00:00Z" }],
    };
  },

  async getMaterials(params?: { category?: string; cefr?: string; search?: string }) {
    const query = params ? `?${new URLSearchParams(params as Record<string, string>).toString()}` : "";
    const live = await liveRequest(`${API_BASE}/materials/${query}`, {});
    if (live !== MOCK) return live;

    let filtered = [...FALLBACK_MATERIALS];
    if (params?.category) {
      filtered = filtered.filter((m) => m.category === params.category);
    }
    if (params?.cefr && params.cefr !== "All Levels") {
      filtered = filtered.filter((m) => m.cefr_level.toLowerCase() === params.cefr!.toLowerCase());
    }
    if (params?.search) {
      const q = params.search.toLowerCase();
      filtered = filtered.filter(
        (m) =>
          m.title.toLowerCase().includes(q) ||
          m.summary.toLowerCase().includes(q) ||
          m.category_display.toLowerCase().includes(q)
      );
    }

    return { results: filtered, count: filtered.length };
  },

  async getMaterialBySlug(slug: string): Promise<MaterialDetail | null> {
    const live = await liveRequest(`${API_BASE}/materials/${slug}/`, {});
    if (live !== MOCK) return live;

    const found = FALLBACK_MATERIALS.find((m) => m.slug === slug || m.id === slug);
    return found || null;
  },

  async getCurrentUser() {
    const live = await liveRequest(`${API_BASE}/auth/me/`, {});
    if (live !== MOCK) return live;
    return null;
  },

  async getEskomStatus(): Promise<EskomStatus> {
    const live = await liveRequest(`${API_BASE}/integrations/eskom/status/`, {});
    if (live !== MOCK) return live;

    throw new Error("Power Guard provider data is unavailable in mock mode.");
  },

  async updatePowerBackup(data: PowerBackupInput) {
    const live = await liveRequest(`${API_BASE}/teachers/profile/power-backup/`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      message: "Power Guard configuration updated successfully.",
      ...data,
    };
  },

  async submitLessonMemo(memoData: PostLessonMemoInput) {
    const live = await liveRequest(`${API_BASE}/bookings/${memoData.booking_id}/memo/`, {
        method: "POST",
        body: JSON.stringify(memoData),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      booking_id: memoData.booking_id,
      status: "memo_submitted",
      message: "Lesson memo submitted. Flashcards generated for student.",
    };
  },

  async getTeacherWallet(): Promise<TeacherWalletData> {
    const live = await liveRequest(`${API_BASE}/payments/wallet/tutor/`, {});
    if (live !== MOCK) return live;

    return {
      pending_escrow_zar: 0,
      cleared_balance_zar: 0,
      fx_context: [],
      payout_bank_account: null,
      transactions: [],
    };
  },

  async getPayoutSettings(): Promise<TeacherPayoutBankAccount> {
    const live = await liveRequest(`${API_BASE}/payments/payout-settings/`, {});
    if (live !== MOCK) return live;
    return { configured: false };
  },

  async updatePayoutSettings(data: TeacherPayoutBankAccountInput): Promise<TeacherPayoutBankAccount> {
    const live = await liveRequest(`${API_BASE}/payments/payout-settings/`, {
        method: "POST",
        body: JSON.stringify(data),
      });
    if (live !== MOCK) return live;

    return { configured: false };
  },

  async saveTeacherAvailability(availability: any) {
    const live = await liveRequest(`${API_BASE}/teachers/availability/manage/`, {
        method: "POST",
        body: JSON.stringify(availability),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      message: "Weekly availability matrix updated and synced to global slot index.",
    };
  },

  async getAdminTelemetry(): Promise<AdminTelemetry> {
    const live = await liveRequest(`${API_BASE}/admin/telemetry/`, {});
    if (live !== MOCK) return live;

    return {
      gmv_today_usd: 1240.0,
      gmv_month_usd: 34850.0,
      active_zoom_sessions_count: 6,
      open_disputes_count: 2,
      pending_vetting_count: 3,
      escrow_liability_usd: 4890.0,
      escrow_liability_zar: 91687.5,
      total_students_count: 1420,
      total_teachers_count: 48,
    };
  },

  async getPendingTeachers(): Promise<PendingTeacherApplication[]> {
    const live = await liveRequest(`${API_BASE}/admin/teachers/pending-vetting/`, {});
    if (live !== MOCK) return live;

    return [
      {
        id: "vet-1",
        full_name: "Thabo Ndlovu",
        email: "thabo.n@example.co.za",
        country: "South Africa (Johannesburg)",
        accent: "South African (Neutral RP)",
        bio: "CELTA-certified English teacher with 4 years tutoring Asian professionals in Tokyo and Taipei. Strong emphasis on business negotiation flow.",
        specialties: ["Business English", "Pronunciation", "STAR Interviewing"],
        video_url: "https://assets.mixkit.co/videos/preview/mixkit-young-man-giving-a-presentation-online-41292-large.mp4",
        tefl_certificate_url: "https://pub-088f123.r2.dev/certificates/thabo-celta.pdf",
        eskom_area: "City of Johannesburg Block 3 - Rosebank",
        has_inverter: true,
        applied_at: "2026-09-29T14:30:00Z",
        status: "pending",
      },
      {
        id: "vet-2",
        full_name: "Kirsty van Zyl",
        email: "kirsty.vz@example.co.za",
        country: "South Africa (Cape Town)",
        accent: "British / SA Hybrid Neutral",
        bio: "Specializing in IELTS preparation and academic writing. Former high school English literature instructor.",
        specialties: ["IELTS Prep", "Grammar Drills", "FreeTalk"],
        video_url: "https://assets.mixkit.co/videos/preview/mixkit-woman-in-online-meeting-41290-large.mp4",
        tefl_certificate_url: "https://pub-088f123.r2.dev/certificates/kirsty-tefl-150hr.pdf",
        eskom_area: "Cape Town City Bowl Area 7",
        has_inverter: true,
        applied_at: "2026-09-30T09:15:00Z",
        status: "pending",
      },
      {
        id: "vet-3",
        full_name: "Zanele Khumalo",
        email: "zanele.k@example.co.za",
        country: "South Africa (Durban)",
        accent: "South African Neutral",
        bio: "Friendly conversationalist focusing on beginners and children. Expert at reducing anxiety in introductory speaking classes.",
        specialties: ["Beginner A1-A2", "Conversation", "Travel English"],
        video_url: "https://assets.mixkit.co/videos/preview/mixkit-young-woman-in-online-meeting-41290-large.mp4",
        tefl_certificate_url: "https://pub-088f123.r2.dev/certificates/zanele-tefl-120hr.pdf",
        eskom_area: "Durban Central Block 1",
        has_inverter: false,
        applied_at: "2026-09-30T11:45:00Z",
        status: "pending",
      },
    ];
  },

  async verifyTeacher(id: string, isVerified: boolean, rejectionReason?: string) {
    const live = await liveRequest(`${API_BASE}/admin/teachers/${id}/verify/`, {
        method: "PATCH",
        body: JSON.stringify({ is_verified: isVerified, rejection_reason: rejectionReason }),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      teacher_id: id,
      is_verified: isVerified,
      message: isVerified ? "Tutor audition approved and published live." : "Application rejected with feedback.",
    };
  },

  async getLiveSessions(): Promise<LiveSessionRadarItem[]> {
    const live = await liveRequest(`${API_BASE}/admin/attendance/live/`, {});
    if (live !== MOCK) return live;

    return [
      {
        id: "sess-1",
        booking_ref: "BK-884192",
        teacher_name: "Sharon M.",
        student_name: "Aiko Tanaka",
        material_title: "Global Remote Work & Digital Nomads",
        start_time_utc: new Date(Date.now() - 12 * 60000).toISOString(),
        elapsed_minutes: 12,
        student_joined_at: new Date(Date.now() - 12 * 60000).toISOString(),
        teacher_joined_at: new Date(Date.now() - 13 * 60000).toISOString(),
        zoom_meeting_id: "987 654 3210",
        status: "active",
      },
      {
        id: "sess-2",
        booking_ref: "BK-884210",
        teacher_name: "Liam O.",
        student_name: "Kenji Sato",
        material_title: "Mastering Cross-Cultural Negotiations",
        start_time_utc: new Date(Date.now() - 22 * 60000).toISOString(),
        elapsed_minutes: 22,
        student_joined_at: new Date(Date.now() - 21 * 60000).toISOString(),
        teacher_joined_at: new Date(Date.now() - 23 * 60000).toISOString(),
        zoom_meeting_id: "987 654 3211",
        status: "wrap_up",
      },
      {
        id: "sess-3",
        booking_ref: "BK-884225",
        teacher_name: "Elena V.",
        student_name: "Marco Rossi",
        material_title: "Travel Anecdotes & Hidden Gems",
        start_time_utc: new Date(Date.now() + 3 * 60000).toISOString(),
        elapsed_minutes: 0,
        teacher_joined_at: new Date(Date.now() - 1 * 60000).toISOString(),
        zoom_meeting_id: "987 654 3212",
        status: "staging",
      },
    ];
  },

  async getDisputes(): Promise<DisputeCase[]> {
    const live = await liveRequest(`${API_BASE}/admin/disputes/`, {});
    if (live !== MOCK) return live;

    return [
      {
        id: "disp-1",
        booking_ref: "BK-779124",
        student_name: "Hiroshi Takahashi",
        teacher_name: "Elena V.",
        lesson_date: "2026-09-29 14:00 SAST",
        amount_usd: 8.0,
        amount_zar: 150.0,
        student_statement: "Tutor did not join the Zoom call for the first 15 minutes. When she joined, audio was stuttering heavily.",
        teacher_statement: "I was present in the meeting at 14:00. The student had incorrect meeting password cached in their browser. I stayed online until 14:25.",
        zoom_telemetry: {
          student_dwell_minutes: 10,
          teacher_dwell_minutes: 25,
          call_connected: true,
          interrupted_reason: "High audio packet loss on student connection node",
        },
        status: "open",
      },
      {
        id: "disp-2",
        booking_ref: "BK-779188",
        student_name: "Yuki Murata",
        teacher_name: "Liam O.",
        lesson_date: "2026-09-29 18:00 SAST",
        amount_usd: 8.0,
        amount_zar: 150.0,
        student_statement: "Session disconnected abruptly at minute 8 due to tutor load shedding.",
        teacher_statement: "Our substation tripped under Stage 4 load shedding. Battery inverter kicked in after 4 minutes, but fiber node remained dead.",
        zoom_telemetry: {
          student_dwell_minutes: 8,
          teacher_dwell_minutes: 8,
          call_connected: false,
          interrupted_reason: "Tutor disconnected abruptly (Socket Reset by Peer)",
        },
        status: "open",
      },
    ];
  },

  async resolveDispute(
    id: string,
    resolution: "full_refund_student" | "release_tutor" | "split_50_50",
    adminNotes?: string
  ) {
    const live = await liveRequest(`${API_BASE}/admin/disputes/${id}/resolve/`, {
        method: "POST",
        body: JSON.stringify({ resolution, admin_notes: adminNotes }),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      dispute_id: id,
      resolution,
      message: `Dispute resolved with action: ${resolution}. Ledger updated atomically.`,
    };
  },

  async getEscrowLedger(): Promise<FinanceEscrowItem[]> {
    const live = await liveRequest(`${API_BASE}/admin/finance/ledger/`);
    if (live !== MOCK) {
      return Array.isArray(live) ? live : (live?.items || []);
    }

    return [];
  },

  async getPayoutBatch(): Promise<PayoutBatchItem[]> {
    const live = await liveRequest(`${API_BASE}/admin/payouts/batch/`, {});
    if (live !== MOCK) return live;

    return [];
  },

  async executePayoutBatch() {
    const live = await liveRequest(`${API_BASE}/admin/payouts/execute-batch/`, {
        method: "POST",
      });
    if (live !== MOCK) return live;

    throw new Error("Payout execution is disabled until an approved banking rail and maker-checker policy exist.");
  },
};

export const bookingApi = api;
export const adminApi = api;
export const teacherOpsApi = api;

// ==========================================
// SLICE 9: STUDENT LEARNING HUB & TUTOR CRM
// ==========================================

export const studentApi = {
  async getStudentLessons(): Promise<StudentLessonItem[]> {
    const live = await liveRequest(`${API_BASE}/student/lessons/`, {});
    if (live !== MOCK) return live;

    return [
      {
        id: "les-101",
        booking_reference: "BK-992144",
        teacher: {
          id: "tut-1",
          name: "Sharon M.",
          avatar: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
          accent: "South African (Neutral)",
        },
        start_time_utc: new Date(Date.now() + 86400000 * 2).toISOString(),
        end_time_utc: new Date(Date.now() + 86400000 * 2 + 1500000).toISOString(),
        local_date: "Tomorrow",
        local_start_time: "15:00",
        local_end_time: "15:25",
        viewer_timezone: "Asia/Tokyo",
        material_title: "AI in Modern Workplaces: Executive Discussion",
        material_cefr: "B2",
        material_slug: "ai-workplace-b2",
        status: "confirmed",
        zoom_url: "https://zoom.us/j/8839201948",
      },
      {
        id: "les-102",
        booking_reference: "BK-884185",
        teacher: {
          id: "tut-1",
          name: "Sharon M.",
          avatar: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
          accent: "South African (Neutral)",
        },
        start_time_utc: "2026-09-28T09:00:00Z",
        end_time_utc: "2026-09-28T09:25:00Z",
        local_date: "Sep 28, 2026",
        local_start_time: "18:00",
        local_end_time: "18:25",
        viewer_timezone: "Asia/Tokyo",
        material_title: "High-Stakes Contract Negotiations",
        material_cefr: "C1",
        material_slug: "high-stakes-negotiations-c1",
        status: "completed",
        memo: {
          id: "mem-102",
          feedback_text: "Outstanding lesson, Kenji! Your articulation of trade-offs was persuasive. Keep prioritizing natural cadence over overly formal passive sentences.",
          vocabulary_words: [
            { word: "concession", definition: "A thing that is granted or yielded, especially in response to demands." },
            { word: "deadlock", definition: "A standstill resulting from opposing forces where no progress can be made." },
            { word: "leverage", definition: "Power to influence a person or situation to achieve desired results." },
          ],
          pronunciation_notes: "Watch out for word stress on 'con-CES-sion', not 'CON-cession'. Keep the 's' sound soft in 'leverage'.",
          grammar_notes: "Remember conditional clause structures: 'If we were to concede on the timeline, we would expect a price rebate.'",
          homework: "Draft 3 bullet points proposing alternative warranty terms for our case study scenario.",
          submitted_at: "2026-09-28T09:32:00Z",
        },
        review: {
          rating: 5,
          tags: ["Patience", "Clear Pronunciation", "Great Corrections"],
          submitted_at: "2026-09-28T10:15:00Z",
        },
      },
      {
        id: "les-103",
        booking_reference: "BK-884012",
        teacher: {
          id: "tut-2",
          name: "David K.",
          avatar: "https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=400&q=80",
          accent: "South African (Neutral)",
        },
        start_time_utc: "2026-09-26T11:00:00Z",
        end_time_utc: "2026-09-26T11:25:00Z",
        local_date: "Sep 26, 2026",
        local_start_time: "20:00",
        local_end_time: "20:25",
        viewer_timezone: "Asia/Tokyo",
        material_title: "Idioms & Conversational Nuances in Global Tech",
        material_cefr: "B2",
        material_slug: "idioms-global-tech-b2",
        status: "completed",
        memo: {
          id: "mem-103",
          feedback_text: "Great conversational rhythm! You quickly grasped the distinction between 'touching base' and 'circling back'.",
          vocabulary_words: [
            { word: "serendipitous", definition: "Occurring or discovered by chance in a happy or beneficial way." },
            { word: "nuance", definition: "A subtle difference or distinction in meaning, expression, or sound." },
          ],
          pronunciation_notes: "Good breath control. Make sure terminal 'th' in 'with' and 'both' is lightly voiced.",
          grammar_notes: "Careful with preposition collocations: 'proficient IN' (not 'proficient AT').",
          homework: "Review your flashcard deck for today's 2 new idioms before next Thursday.",
          submitted_at: "2026-09-26T11:30:00Z",
        },
        // Awaiting review
      },
      {
        id: "les-104",
        booking_reference: "BK-883905",
        teacher: {
          id: "tut-3",
          name: "Liam O.",
          avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80",
          accent: "South African (Neutral)",
        },
        start_time_utc: "2026-09-22T08:00:00Z",
        end_time_utc: "2026-09-22T08:15:00Z",
        local_date: "Sep 22, 2026",
        local_start_time: "17:00",
        local_end_time: "17:15",
        viewer_timezone: "Asia/Tokyo",
        material_title: "Green Energy Transition in Developing Economies",
        material_cefr: "B2",
        material_slug: "green-energy-b2",
        status: "interrupted_power",
        memo: undefined,
      },
    ];
  },

  async getStudentFlashcards(): Promise<StudentFlashcard[]> {
    const live = await liveRequest(`${API_BASE}/student/flashcards/`, {});
    if (live !== MOCK) return live;

    return [
      {
        id: "card-1",
        word: "concession",
        phonetic: "/kənˈseʃ.ən/",
        part_of_speech: "noun",
        definition: "A thing that is granted, especially in response to demands or to reach an agreement.",
        example_sentence: "The union made significant wage concessions during the quarterly collective bargaining talks.",
        lesson_source: "High-Stakes Contract Negotiations (Sharon M.)",
        mastery: "learning",
        review_count: 3,
        next_review_due: "2026-10-01",
      },
      {
        id: "card-2",
        word: "deadlock",
        phonetic: "/ˈded.lɒk/",
        part_of_speech: "noun",
        definition: "A situation, typically one involving opposing parties, in which no progress can be made.",
        example_sentence: "After five hours of intense debate, the cross-border trade talks reached an agonizing deadlock.",
        lesson_source: "High-Stakes Contract Negotiations (Sharon M.)",
        mastery: "new",
        review_count: 0,
        next_review_due: "2026-09-30",
      },
      {
        id: "card-3",
        word: "serendipitous",
        phonetic: "/ˌser.ənˈdɪp.ɪ.təs/",
        part_of_speech: "adjective",
        definition: "Occurring or discovered by chance in a happy or beneficial way.",
        example_sentence: "Their partnership was serendipitous, beginning with a casual chat at an airport terminal.",
        lesson_source: "Idioms & Conversational Nuances (David K.)",
        mastery: "learning",
        review_count: 4,
        next_review_due: "2026-10-02",
      },
      {
        id: "card-4",
        word: "nuance",
        phonetic: "/ˈnjuː.ɑːns/",
        part_of_speech: "noun",
        definition: "A subtle difference or distinction in expression, meaning, response, or tone.",
        example_sentence: "Skilled international negotiators listen closely to the cultural nuances in speech pauses.",
        lesson_source: "Idioms & Conversational Nuances (David K.)",
        mastery: "mastered",
        review_count: 8,
        next_review_due: "2026-10-15",
      },
      {
        id: "card-5",
        word: "mitigate",
        phonetic: "/ˈmɪt.ɪ.ɡeɪt/",
        part_of_speech: "verb",
        definition: "Make something bad or harmful less severe, serious, or painful.",
        example_sentence: "Installing battery back-up solutions helped the remote engineering team mitigate grid outages.",
        lesson_source: "Curriculum: AI & Infrastructure",
        mastery: "new",
        review_count: 1,
        next_review_due: "2026-09-30",
      },
      {
        id: "card-6",
        word: "leverage",
        phonetic: "/ˈliː.vər.ɪdʒ/",
        part_of_speech: "verb / noun",
        definition: "Use something to maximum advantage; the exertive power to influence outcomes.",
        example_sentence: "The startup leveraged its patent portfolio to secure favorable term sheets.",
        lesson_source: "High-Stakes Contract Negotiations (Sharon M.)",
        mastery: "mastered",
        review_count: 6,
        next_review_due: "2026-10-14",
      },
    ];
  },

  async updateFlashcardMastery(
    cardId: string,
    grade: "again" | "good" | "easy"
  ): Promise<{ success: boolean; nextReview: string; mastery: "new" | "learning" | "mastered" }> {
    const live = await liveRequest(`${API_BASE}/student/flashcards/${cardId}/mastery/`, {
        method: "POST",
        body: JSON.stringify({ grade }),
      });
    if (live !== MOCK) return live;

    const masteryResult = grade === "easy" ? "mastered" : grade === "good" ? "learning" : "new";
    const daysToAdd = grade === "easy" ? 7 : grade === "good" ? 3 : 1;
    const nextDate = new Date(Date.now() + daysToAdd * 86400000).toISOString().split("T")[0];

    return {
      success: true,
      nextReview: nextDate,
      mastery: masteryResult,
    };
  },

  async submitLessonReview(
    bookingId: string,
    rating: number,
    tags: string[],
    privateNotes?: string
  ): Promise<{ success: boolean; message: string }> {
    const live = await liveRequest(`${API_BASE}/student/bookings/${bookingId}/review/`, {
        method: "POST",
        body: JSON.stringify({ rating, tags, private_notes: privateNotes }),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      message: "Thank you! Your confidential 5-star rubric review has been recorded.",
    };
  },

  async getStudentProfile(): Promise<StudentProfileData> {
    const live = await liveRequest(`${API_BASE}/student/profile/`, {});
    if (live !== MOCK) return live;

    return {
      id: "stu-1",
      full_name: "Kenji Sato",
      email: "kenji.sato@example.jp",
      country: "Japan",
      timezone: "Asia/Tokyo",
      target_level: "C1 - Advanced Fluency",
      learning_goals: "Conduct seamless cross-border product design reviews, speak persuasively in tech board meetings without translation latency, and expand active idiomatic vocabulary.",
    };
  },

  async updateStudentProfile(
    data: Partial<StudentProfileData>
  ): Promise<{ success: boolean; profile: StudentProfileData }> {
    const live = await liveRequest(`${API_BASE}/student/profile/`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      profile: {
        id: "stu-1",
        full_name: data.full_name || "Kenji Sato",
        email: data.email || "kenji.sato@example.jp",
        country: data.country || "Japan",
        timezone: data.timezone || "Asia/Tokyo",
        target_level: data.target_level || "C1 - Advanced Fluency",
        learning_goals: data.learning_goals || "Speak persuasively in tech board meetings.",
      },
    };
  },
};

export const teacherCrmApi = {
  async getTeacherStudentsDossier(): Promise<TeacherStudentDossierItem[]> {
    const live = await liveRequest(`${API_BASE}/teacher/students/`, {});
    if (live !== MOCK) return live;

    return [
      {
        id: "dos-1",
        student_id: "stu-1",
        student_name: "Kenji Sato",
        student_email: "kenji.sato@example.jp",
        student_country: "Japan",
        target_level: "C1",
        lessons_completed_count: 14,
        last_lesson_date: "2026-09-28",
        private_pedagogical_notes: "Very diligent with vocabulary flashcards. Tends to over-rely on formal passive voice when discussing technical architecture. Encourage colloquial phrasal verbs and rapid-fire scenario debates.",
        common_grammar_mistakes: [
          "Article omission ('the / a')",
          "Second conditional inversion ('If I would have...')",
          "Preposition collocations ('interested on' instead of 'interested in')",
        ],
      },
      {
        id: "dos-2",
        student_id: "stu-2",
        student_name: "Marco Rossi",
        student_email: "marco.rossi@example.it",
        student_country: "Italy",
        target_level: "B2",
        lessons_completed_count: 8,
        last_lesson_date: "2026-09-29",
        private_pedagogical_notes: "High enthusiasm and energetic delivery. Needs ongoing focus on terminal consonant articulation ('think' vs 'thing'). Enjoys Daily News articles on automotive and green energy.",
        common_grammar_mistakes: [
          "False friends ('actually' vs 'currently')",
          "Word order in indirect questions ('Can you tell me where is it' -> 'where it is')",
        ],
      },
      {
        id: "dos-3",
        student_id: "stu-3",
        student_name: "Min-ji Kim",
        student_email: "minji.kim@example.kr",
        student_country: "South Korea",
        target_level: "B1",
        lessons_completed_count: 5,
        last_lesson_date: "2026-09-25",
        private_pedagogical_notes: "Exceptional reading comprehension, but hesitates during spontaneous FreeTalk. Best results observed when reading article paragraph out loud first to build vocal warmth.",
        common_grammar_mistakes: [
          "Pronoun gender slip ('he/she' interchange)",
          "Plural noun agreement with uncountables ('informations', 'advices')",
        ],
      },
    ];
  },

  async updateTeacherStudentDossier(
    studentId: string,
    notes: string,
    commonMistakes?: string[]
  ): Promise<{ success: boolean; message: string }> {
    const live = await liveRequest(`${API_BASE}/teacher/students/${studentId}/dossier/`, {
        method: "PATCH",
        body: JSON.stringify({ private_pedagogical_notes: notes, common_grammar_mistakes: commonMistakes }),
      });
    if (live !== MOCK) return live;

    return {
      success: true,
      message: "Student pedagogical dossier updated successfully.",
    };
  },
};

// Direct convenience exports for imports
export const getStudentLessons = studentApi.getStudentLessons;
export const getStudentFlashcards = studentApi.getStudentFlashcards;
export const updateFlashcardMastery = studentApi.updateFlashcardMastery;
export const submitLessonReview = studentApi.submitLessonReview;
export const getStudentProfile = studentApi.getStudentProfile;
export const updateStudentProfile = studentApi.updateStudentProfile;
export const getTeacherStudentsDossier = teacherCrmApi.getTeacherStudentsDossier;
export const updateTeacherStudentDossier = teacherCrmApi.updateTeacherStudentDossier;
