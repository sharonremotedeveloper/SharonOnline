# Model Context Protocol (MCP) Integration for AI Agents — ARCHITECTURE & STAGE MAPPING

**Status:** PENDING — Mapped to **Phase 17 / Phase 2 Post-MVP Scope (Post-Launch AI Expansion)**  
**Target Audience:** Anesu MUPESA (Lead Architect) & All Collaborating AI Agents (Antigravity, Claude, Codex)  
**Recorded:** 2026-10-18  

---

## 1. Executive Summary & Core Concept

**Model Context Protocol (MCP)** is an open, standardized protocol (originated by Anthropic and adopted across the AI industry) that enables AI models and autonomous agents to securely connect to tools, services, and data repositories over a unified interface (analogous to **"USB-C for AI agents"**).

### Why MCP for Sharon's ESL Platform?
Currently, our backend integrates external services (PayFast, PayPal, Daily.co, Google Calendar, EskomSePush, Resend) via dedicated Django service classes and Celery tasks. 

As we introduce intelligent conversational agents, automated lesson assistants, and administrative copilots:
1. **Without MCP (Brittle):** Every AI agent requires bespoke prompt engineering, custom JSON function-calling schemas, manual token plumbing, and fragile point-to-point glue code.
2. **With MCP (Standardized & Pluggable):** Our platform exposes its domain capabilities (tutor search, booking engine, CEFR curriculum reader, SRS flashcards) as standard MCP tools. Any AI agent (internal student copilot, tutor lesson prep assistant, or external agent in Claude Desktop/Cursor) can instantly discover and execute permitted operations through a uniform, type-safe protocol.

---

## 2. Dual-Mode Architecture

```mermaid
flowchart TD
    subgraph Agent Runtime [AI Agent Clients]
        A1["Student Matchmaker Copilot"]
        A2["Tutor Lesson Prep Assistant"]
        A3["Admin Operations & DLQ Agent"]
    end

    subgraph MCP Client Runtime [Platform MCP Client Layer]
        MC["Python MCP Client / LangGraph / LiteLLM"]
    end

    subgraph Internal MCP Server [Sharon Online MCP Server (apps.mcp)]
        T1["search_tutors(accent, tags, rate)"]
        T2["get_tutor_availability(id, date)"]
        T3["reserve_booking_slot(student_id, slot_id)"]
        T4["get_cefr_material(slug)"]
        T5["create_srs_flashcard(student_id, term, def)"]
        T6["draft_lesson_memo(booking_id, notes)"]
    end

    subgraph External MCP Servers [Third-Party MCP Servers]
        E1["Google Calendar MCP Server"]
        E2["Notion Knowledge Base MCP"]
        E3["Playwright Browser MCP"]
    end

    A1 & A2 & A3 --> MC
    MC <-->|JSON-RPC / SSE / STDIO| Internal MCP Server
    MC <-->|JSON-RPC / SSE / STDIO| External MCP Servers
    Internal MCP Server <-->|Service Layer & ORM| DjangoDB[(PostgreSQL / Redis)]
```

### Mode 1: Sharon Online as an MCP Server (Platform Provider)
The Django backend exposes our business domain through a sandboxed MCP server:
* Exposes tools: `get_tutors`, `check_availability`, `reserve_slot`, `get_lesson_material`, `create_srs_card`.
* Authenticated via scoped machine API tokens (JWT / HMAC API keys).
* Enforces the existing domain invariants (Redlock 10-minute hold, transaction integrity, cancellation policies).

### Mode 2: Sharon Online as an MCP Client (Consumer)
The platform hosts background AI agents (running via Celery worker pools or asynchronous services) that connect to both internal and external MCP servers:
* Notion MCP (reading pedagogical guidelines or staff memos).
* Google Calendar MCP (evaluating tutor schedule conflicts).
* Storage / Media MCP (processing lesson audio/video telemetry).

---

## 3. Stage & Roadmap Mapping

To preserve launch velocity and financial safety, MCP integration is mapped to **Phase 17 (Post-Launch AI Expansion)**, immediately following the commercial launch and UAT hardening of the MVP (Phases 1-16).

| Stage | Milestone | Dependencies | Scope & Deliverables |
| :--- | :--- | :--- | :--- |
| **Stage 17.1** | **MCP Server Core Scaffolding** | Phase 10 (Payments), Phase 11 (Tutor Lifecycle) | Install official Python MCP SDK (`mcp` / `fastmcp`). Scaffold `backend/apps/mcp/` with server initialization, auth middleware, and stdio/SSE transports. |
| **Stage 17.2** | **Read-Only Discovery Tools** | Stage 17.1, Phase 2 / Stage 2.6 | Expose read-only MCP tools: tutor faceted query, verified rating retrieval, CEFR curriculum exploration, and slot availability snapshots. |
| **Stage 17.3** | **Transactional Mutating Tools** | Stage 17.2, Phase 9 (Booking Core), Phase 12 | Expose write tools with strict transaction fences: Redlock slot reservation, SRS flashcard generation, draft lesson memo submission. |
| **Stage 17.4** | **Agent Client Runtime & Copilots** | Stage 17.3, Stage 6.6, Stage 8.6 | Connect conversational student copilot on Next.js frontend to backend MCP client; enable automated post-lesson vocabulary extractor. |
| **Stage 17.5** | **Staff & Ops Admin MCP Copilot** | Stage 17.4, Phase 15 / Task 15.4 | Connect administrative LLM agent to inspect webhook Dead Letter Queues (DLQ), audit payout batch invariants, and query Eskom outage buffers. |

---

## 4. Key Capabilities & Capabilities Unlocked

1. **Intelligent Student-Tutor Matchmaker:**  
   Students can express nuanced goals in natural language (*"Find me a South African tutor with a British or neutral accent free on Wednesday at 18:00 JST for IELTS speaking prep"*). The agent uses MCP tools to query tutor profiles, verify timezone overlap, check real availability, and initiate the booking hold.
2. **Automated Post-Lesson Memos & SRS Deck Feeding:**  
   After a 25-minute lesson, an AI agent ingests the teacher's rough lesson notes or audio transcript (via Daily.co telemetry), extracts key vocabulary, grammar corrections, and CEFR-graded practice sentences, and calls `create_srs_flashcard` to deposit cards directly into the student's Spaced Repetition System.
3. **Curriculum & Lesson Copilot for Tutors:**  
   Tutors can prompt an in-classroom AI assistant to suggest CEFR-aligned discussion questions, generate instantaneous role-play scenarios, or pull matching reading articles on the fly.
4. **Model & Provider Agnosticism:**  
   Because MCP standardizes tool definitions and context exchange, the platform is never locked into a single AI provider. We can freely run Claude 3.5 Sonnet, Gemini 1.5/2.0 Pro, GPT-4o, or local open-source models (via Ollama or vLLM) using the exact same MCP tools.

---

## 5. Security & Safety Invariants (Strict Protocol)

All AI agent interactions via MCP must obey the platform's core security rules:

1. **Role-Based Access Control (RBAC):**  
   - Student agents cannot access staff or payout tools.  
   - Tutor agents can only mutate lesson memos and view dossiers for students they have actively taught.  
2. **Financial Air-Gap (Human-in-the-Loop):**  
   - **NO MCP tool may autonomously execute live financial payouts, refunds, or wallet balance adjustments.**  
   - Financial tools are strictly read-only or produce "draft requests" requiring human staff confirmation in the Django admin or Admin Command Center (`ADM-05/06`).  
3. **Rate Limiting & Cost Guardrails:**  
   - Every MCP agent request is subject to per-session token limits and Redis-backed rate throttles to protect LLM inference budgets and upstream database capacity.  
4. **Audit Logging:**  
   - All tool invocations executed by AI agents are permanently logged in `apps.crm` / `apps.mcp.models.ToolInvocationLog` with actor identity, input arguments, execution timestamp, and status.
