export interface LegalPolicy {
  slug: string;
  title: string;
  shortTitle: string;
  lastUpdated: string;
  summary: string;
  markdownContent: string;
}

export const LEGAL_POLICIES: Record<string, LegalPolicy> = {
  terms: {
    slug: "terms",
    title: "Terms of Service & Platform Agreement",
    shortTitle: "Terms of Service",
    lastUpdated: "October 6, 2026",
    summary: "The legally binding terms governing your access to and use of the Sharon Online synchronous tutoring marketplace.",
    markdownContent: `
## 1. Introduction and Acceptance of Terms

Welcome to Sharon Online. These Terms of Service ("Terms") constitute a legally binding agreement between you ("User", "Student", or "Teacher") and Sharon Online (Pty) Ltd. ("Sharon Online", "we", "us", or "our"), a company incorporated in accordance with the company laws of the Republic of South Africa.

By registering an account, purchasing lesson credits, booking a session, or using our web application, you acknowledge that you have read, understood, and agree to be bound by these Terms and our Privacy Policy. If you do not agree to these Terms, you must not access or use the platform.

## 2. Description of the Marketplace

Sharon Online operates an online marketplace and synchronous education technology infrastructure connecting accredited South African English language educators ("Tutors") with students located globally ("Students") for private, live 25-minute lessons.

Sharon Online provides:
- Live calendar scheduling, slot reservation, and automated timezone synchronization.
- Synchronous high-definition video classrooms with interactive lesson materials and audio tools.
- Post-lesson pedagogic documentation, including grammar feedback, vocabulary flashcards, and homework tracking.
- Multi-currency payment processing, escrow protection, and tutor payout disbursements.

Sharon Online is not an employer of Tutors. Tutors are independent professional contractors who provide educational services directly to Students subject to our vetting and performance standards.

## 3. Account Registration and Eligibility

To access our educational services:
- You must be at least 18 years of age, or have the express consent and supervision of a parent or legal guardian.
- You agree to provide accurate, current, and complete registration information.
- You are solely responsible for maintaining the confidentiality of your account credentials and for all activities that occur under your account.
- You must notify Sharon Online immediately upon discovering any unauthorized use or breach of security.

## 4. Lesson Credits, Purchases, and Pricing

1. **Credit Model**: Educational services are acquired through pre-purchased lesson credits or single lesson checkouts. One lesson credit entitles the student to one 25-minute synchronous private lesson with any verified tutor on the platform.
2. **Pricing & Currencies**: All lesson prices and package rates are displayed transparently in South African Rand (ZAR), United States Dollars (USD), Euros (EUR), and Japanese Yen (JPY). All transactions are processed through authorized payment gateways (PayFast and PayPal).
3. **Credit Expiration**: Purchased lesson credit packages expire 30 days after the date of grant. Any unused credits at the end of the 30-day period lapse without refund, unless extended due to verified medical emergencies or platform outages.

## 5. Conduct and Community Standards

Users must uphold the highest standards of integrity, mutual respect, and academic ethics:
- **Zero Harassment**: Abusive, threatening, discriminatory, sexually explicit, or harassing language or behavior will result in immediate and permanent account termination.
- **No Disintermediation**: Users agree not to solicit or accept payments outside the Sharon Online platform, nor exchange personal contact information (including personal WhatsApp, Skype, or bank accounts) for off-platform commercial lessons.
- **Classroom Punctuality**: Students and Tutors are expected to enter the classroom promptly at the scheduled start time. Tutors arriving more than 5 minutes late are subject to platform strikes and penalty reviews.

## 6. Intellectual Property Rights

1. **Curriculum Materials**: All curriculum slide decks, reading texts, audio recordings, and lesson exercises provided on Sharon Online are the proprietary property of Sharon Online (Pty) Ltd. or its licensors. You may not distribute, reproduce, or resell these materials.
2. **User Notes & Memos**: Students retain non-exclusive ownership of their personal notes. Post-lesson memos created by tutors remain accessible to the student for continuous educational review.

## 7. Limitation of Liability and Governing Law

To the maximum extent permitted by applicable law, Sharon Online shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising from the use of or inability to use our services.

These Terms shall be governed by and construed in accordance with the laws of the Republic of South Africa. Any disputes arising out of or in connection with these Terms shall be subject to the exclusive jurisdiction of the courts located in Cape Town, Western Cape, South Africa.
    `.trim(),
  },

  privacy: {
    slug: "privacy",
    title: "Privacy & Data Protection Policy (POPIA & GDPR)",
    shortTitle: "Privacy Policy",
    lastUpdated: "October 6, 2026",
    summary: "How Sharon Online collects, processes, protects, and respects your personal information in compliance with POPIA, GDPR, and APPI.",
    markdownContent: `
## 1. Commitment to Privacy

Sharon Online (Pty) Ltd. ("Sharon Online") is committed to safeguarding the privacy and personal information of our students, teachers, and website visitors. This Privacy Policy details our practices concerning personal data collection, processing, storage, and cross-border transfer.

Our policies comply with:
- **POPIA**: The Protection of Personal Information Act No. 4 of 2013 (South Africa).
- **GDPR**: The General Data Protection Regulation (Regulation EU 2016/679).
- **APPI**: The Act on the Protection of Personal Information (Japan).

## 2. Personal Information We Collect

We collect information necessary to provide synchronous educational services:
1. **Account Information**: Full name, email address, password hash, country of residence, IANA timezone, and optional phone number.
2. **Student Profile Data**: Target English proficiency level (CEFR), specific learning objectives, and vocabulary acquisition records.
3. **Tutor Professional Data**: Audio audition files, video introductions, TEFL/TESOL teaching credentials, identity verification documents, and South African banking details for EFT disbursements.
4. **Classroom Telemetry**: Join and leave timestamps, connection quality metrics, attendance status, and automated session audit records.
5. **Payment Information**: Transaction identifiers, billing currency, and receipt histories. Credit card numbers and PayPal credentials are processed directly by compliant PCI-DSS Level 1 payment processors and are never stored on our servers.

## 3. Lawful Basis and Purpose of Processing

We process your data strictly under the following lawful bases:
- **Contractual Necessity**: To deliver scheduled lessons, maintain credit balances, process payments, and pay tutor earnings.
- **Legal Compliance**: To fulfill tax accounting obligations, South African Reserve Bank reporting, and child safeguarding mandates.
- **Legitimate Interests**: To detect and prevent fraud, optimize video call latency, and enforce platform anti-harassment standards.
- **Consent**: For optional promotional communications, cookie tracking, and student feedback surveys.

## 4. Cross-Border Data Transfers

Because Sharon Online connects South African educators with students worldwide, personal information may be transmitted and stored in secure cloud data centers located in South Africa, the European Union, the United Kingdom, and the United States (via Cloudflare and Amazon Web Services).

All cross-border data transfers are executed under strict contractual safeguards, ensuring that recipient jurisdictions maintain data protection standards substantially similar to POPIA Condition 12 and GDPR Chapter V.

## 5. Data Retention Schedules

- **Account Data**: Retained for the lifetime of your active account plus 3 years following account closure.
- **Financial & Tax Records**: Retained for 5 years in compliance with the South African Tax Administration Act.
- **Attendance & Telemetry Logs**: Retained for 90 days for dispute resolution and quality auditing, after which logs are anonymized.
- **Support Inquiries**: Retained for 12 months following resolution.

## 6. Your Rights (SAR & Rectification)

Under POPIA Section 23 and GDPR Article 15, you have comprehensive rights over your personal data:
- **Right to Access (SAR)**: You may request a complete, machine-readable export of all personal data held about you at any time via our automated Subject Access Request pipeline (\`GET /api/v1/auth/me/data-export/\`).
- **Right to Rectification**: You can update your contact information, timezone, or profile details at any time in your account settings.
- **Right to Erasure**: You may request permanent deletion of your profile, subject to statutory tax and financial retention laws.
- **Right to Object**: You may opt out of non-essential communications and marketing notifications.

To contact our Data Protection Officer, email **privacy@sharonesl.com**.
    `.trim(),
  },

  refunds: {
    slug: "refunds",
    title: "Lesson Cancellation, Rescheduling & Refund Policy",
    shortTitle: "Refund Policy",
    lastUpdated: "October 6, 2026",
    summary: "Transparent rules governing student cancellations, tutor rescheduling, 24-hour escrow release, and Eskom load shedding protections.",
    markdownContent: `
## 1. Principles of Fair Booking

Synchronous language learning requires time commitment from both learners and educators. Our cancellation and refund policy is engineered to protect students' financial investments while fairly compensating tutors for their scheduled time.

All bookings are protected by Sharon Online's **24-Hour Escrow Clearing Engine**: tutor compensation is held in secure escrow until a lesson is confirmed delivered without unresolved disputes.

## 2. Student Cancellations and Rescheduling

1. **Advance Notice (> 24 Hours Before Lesson Start)**:
   - A student may cancel or reschedule a confirmed booking at zero penalty.
   - If paid via lesson credit, the credit is immediately returned to the student's active wallet balance with full validity.
   - If paid via instant single-checkout, the funds are credited back as a reusable lesson ticket or refunded to the original payment method upon request.

2. **Late Notice (< 24 Hours Before Lesson Start)**:
   - Cancellations made less than 24 hours prior to class start are categorized as **Late Cancellations**.
   - Because the tutor reserved the discrete 25-minute timeslot and cannot easily re-book it on short notice, the student forfeits the lesson credit or payment.
   - The lesson fee is disbursed to the tutor in accordance with platform payout schedules.

3. **Student No-Show (T+10 Minutes)**:
   - If a student fails to enter the classroom within 10 minutes of the scheduled start time, the lesson is designated as a Student No-Show.
   - The lesson is marked completed, the credit is consumed, and the tutor is compensated in full.

## 3. Tutor Cancellations and Rescheduling

We hold our educators to strict professional attendance standards:
- **Tutor Cancellation (> 24 Hours)**: The student receives an immediate 100% credit refund and an automated priority notification to choose an alternative tutor.
- **Late Tutor Cancellation (< 24 Hours) or Tutor No-Show**:
  1. The student is immediately refunded their lesson credit.
  2. The student receives one **Complimentary Goodwill Bonus Credit** added to their account.
  3. The tutor receives an automatic platform SLA strike. Tutors accumulating 3 strikes within a rolling 90-day window are automatically suspended pending administrative review.

## 4. Eskom Load Shedding & Power Outage Shield

Because our educators reside in South Africa, our platform features the **Eskom Load Shedding Shield**:
- All verified tutors are required to maintain a battery inverter/UPS backup and secondary LTE cellular failover.
- If an unscheduled electrical grid failure or severe weather disrupts a tutor's connection during a class:
  1. The student receives an immediate full credit refund.
  2. The occurrence is audited against municipal Eskom grid schedules. If verified as an involuntary infrastructure outage, the tutor's account is protected from SLA strikes.

## 5. Credit Pack Purchases and Monetary Refunds

1. **Unused Credit Packs**: If you purchase a lesson pack and change your mind, you may request a full monetary refund to your original payment method within **7 calendar days** of purchase, provided that zero credits from the pack have been consumed.
2. **Partially Used Packs**: Once any credit from a pack has been used, monetary refunds are not available; however, remaining credits remain valid for the full 30-day lifecycle.
3. **Disputes**: If you experienced technical disruptions or substandard teaching, submit a dispute within 24 hours of class completion via **support@sharonesl.com** for prompt human mediation.
    `.trim(),
  },

  "child-safety": {
    slug: "child-safety",
    title: "Child Safeguarding & Safety Policy",
    shortTitle: "Child Safeguarding",
    lastUpdated: "October 6, 2026",
    summary: "Our zero-tolerance standards, teacher screening procedures, and safeguards to protect young learners in our global community.",
    markdownContent: `
## 1. Zero-Tolerance Safety Commitment

Sharon Online is uncompromising in its dedication to the safety, dignity, and wellbeing of every child and young learner who accesses our digital platform. We maintain a zero-tolerance policy regarding child abuse, exploitation, grooming, emotional harassment, or inappropriate conduct of any kind.

Every lesson with a student under the age of 18 is treated with the highest degree of safeguarding scrutiny.

## 2. Tutor Vetting and Background Verification

Before any educator is permitted to accept bookings on Sharon Online, they must complete our rigorous multi-stage vetting process:
1. **Identity & Criminal Clearance**: Verified South African National ID verification and background clearance checks.
2. **Academic & TEFL Certification**: Mandatory validation of accredited 120+ hour TEFL/TESOL certification and university degrees.
3. **Pedagogic Audition**: Live interview and recorded pedagogical audition evaluated by senior academic supervisors against strict communication and classroom demeanor rubrics.
4. **Safeguarding Training**: Mandatory completion of Sharon Online's Child Safeguarding & Behavioral Ethics LMS training module prior to slot unlocking.

## 3. Classroom Standards and Behavioral Protocols

During all synchronous video sessions involving minors:
- **Professional Attire & Environment**: Tutors must conduct lessons in a quiet, well-lit, professional setting with neutral backgrounds.
- **Appropriate Content Only**: Curriculum materials must remain strictly age-appropriate, focusing exclusively on language learning, grammar, vocabulary, and cultural exchange.
- **No Private Off-Platform Communication**: Tutors and students are expressly prohibited from exchanging private personal contacts (such as personal phone numbers, social media handles, Discord, WhatsApp, or email). All interaction must occur inside Sharon Online.
- **Parental Presence Welcome**: Parents or legal guardians have the absolute right to be present in the room or observe any lesson at any time without advance notice.

## 4. Automated Session Telemetry and Audit Logging

To guarantee total accountability:
- Automated audit systems record connection metadata, attendee presence timestamps, and video session logs.
- Lesson recordings and chat logs are stored in encrypted, access-restricted private storage for a mandatory 30-day safeguarding audit window.
- Access to safeguarding audit logs is strictly restricted to our vetted Child Protection Officers and certified law enforcement entities upon valid legal process.

## 5. Incident Reporting and Immediate Escalation Protocol

If a student, parent, or tutor observes any behavior that causes discomfort or raises safety concerns:
1. **In-Class Exit**: Either party may immediately exit the lesson without penalty.
2. **Emergency Safeguarding Contact**: Reports can be submitted 24/7 to **safety@sharonesl.com** with the subject line "URGENT: SAFEGUARDING REPORT".
3. **Immediate Suspension**: Upon receipt of a credible safeguarding report, the reported user's account is instantly suspended, future bookings are cancelled with full student refunds, and a formal investigation is initiated within 2 hours.
    `.trim(),
  },

  cookies: {
    slug: "cookies",
    title: "Cookie & Tracking Technology Policy",
    shortTitle: "Cookie Policy",
    lastUpdated: "October 6, 2026",
    summary: "Clear disclosure of the cookies, local storage tokens, and web technologies used to operate Sharon Online securely.",
    markdownContent: `
## 1. What Are Cookies?

Cookies and local storage are small text files or data structures placed on your computer, tablet, or smartphone when you visit a website. They are widely used to make web applications work efficiently, provide secure authentication, and supply analytical insights to site operators.

## 2. Categories of Cookies We Use

Sharon Online categorizes cookies into three distinct tiers:

### A. Strictly Necessary (Essential) Cookies
These cookies and storage tokens are indispensable for the website to function. They enable core security features, authentication sessions, and transaction integrity.
- **Session Auth Tokens (\`access_token\`, \`refresh_token\`)**: HttpOnly, secure cookies that authenticate your user account without exposing credentials to malicious scripts.
- **CSRF Token (\`csrftoken\`)**: Protects your account against Cross-Site Request Forgery attacks during checkout and form submissions.
- **Load Balancer Routing**: Ensures your requests are consistently routed to the lowest-latency edge server.
*Consent is not optional for Strictly Necessary Cookies, as the platform cannot function without them.*

### B. Functional & Preference Cookies
These cookies remember choices you make to personalize and enhance your user experience:
- **Currency Preference (\`sharon_currency\`)**: Remembers whether you prefer browsing lesson prices in USD, ZAR, EUR, or JPY.
- **Timezone Preference**: Stores your chosen IANA timezone to render live tutor calendars correctly without constant manual selection.
- **Cookie Consent State (\`sharon_cookie_consent_v1\`)**: Remembers your cookie consent choices so you are not prompted repeatedly.

### C. Performance & Analytics Cookies (Optional)
These cookies help us understand how learners and educators navigate Sharon Online, which pages are most popular, and where video connection latency can be improved.
- **Aggregated Telemetry**: Anonymized metrics on page load speeds, error rates, and user journeys.
- **No Third-Party Ad Trackers**: Sharon Online does not sell your personal data or partner with predatory advertising tracking networks.

## 3. Managing and Revoking Your Consent

When you first visit Sharon Online, our WCAG-compliant Cookie Consent Banner allows you to:
- **Accept All Cookies**: Enables essential, functional, and performance analytics cookies.
- **Reject Non-Essential**: Restricts cookie usage strictly to essential authentication and security tokens.
- **Customize Preferences**: Allows granular selection of analytics and preference cookies.

You can modify your preferences at any time by clearing your browser cache or clicking "Cookie Preferences" in the website footer.

## 4. Updates to This Policy

We may update this Cookie Policy periodically to reflect technological advancements or regulatory requirements. Any updates will be published with a revised "Last Updated" timestamp.
    `.trim(),
  },
};
