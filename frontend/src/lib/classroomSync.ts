/**
 * Classroom Material Synchronization Coordinator (Milestone 3 / Requirement R3)
 *
 * Implements real-time peer-to-peer curriculum synchronization over WebRTC DataChannels
 * (Daily.co sendAppMessage and app-message event bus) for Sharon Online:
 * - Strongly typed message envelopes: { type, payload, senderId, role, timestamp }
 * - Message types: SYNC_TAB, SYNC_PAGE, SYNC_SCROLL, SYNC_HIGHLIGHT, CLASSROOM_MATERIAL_SYNC, SYNC_CONTROL
 * - Role-based authority (Teacher authoritative, student interactive mode toggle)
 * - Multi-layer echo prevention (re-entrancy suppression, self-message drop, scroll deadband)
 * - Monotonic Last-Write-Wins (LWW) timestamp ordering
 * - Student "Follow Tutor" state machine (enabled by default, background caching, instant snap-back)
 * - Pure TypeScript with ZERO DOM dependencies (window, document)
 */

export type SyncRole = "teacher" | "student";
export type UserRole = SyncRole;

export interface TrustedSyncSender {
  senderId: string;
  role: SyncRole;
}

export type CurriculumTabId = "article" | "vocab" | "questions";
export type ReaderTab = CurriculumTabId;

export type HighlightAction = "set" | "clear";

export type ClassroomSyncMessageType =
  | "SYNC_TAB"
  | "SYNC_PAGE"
  | "SYNC_SCROLL"
  | "SYNC_HIGHLIGHT"
  | "CLASSROOM_MATERIAL_SYNC"
  | "SYNC_CONTROL";

export interface HighlightAttribution {
  senderId: string;
  role: SyncRole;
  name?: string;
}

export interface SyncHighlightPayload {
  action: HighlightAction;
  highlightId?: string;
  vocabIndex?: number | null;
  sectionId?: string;
  textRange?: {
    startOffset: number;
    endOffset: number;
    text?: string;
  };
  color?: string;
  attributedTo: HighlightAttribution;
  timestamp: number;
}

export interface SyncTabPayload {
  tab: CurriculumTabId;
  tabIndex: number; // 0 = 'article', 1 = 'vocab', 2 = 'questions'
}

export interface SyncPagePayload {
  page: number; // 1-based index or section index
  totalPages?: number;
  materialId?: string | null;
}

export interface SyncScrollPayload {
  scrollOffset: number; // Normalized [0.0, 1.0]
  scrollY?: number;
  progress?: number;
  source?: "reader" | "document";
}

export interface ClassroomMaterialSyncPayload {
  materialId: string | null;
  sectionIndex: number; // 0: article, 1: vocab, 2: questions
  highlightedVocabIndex: number | null;
  activeTab?: string;
  scrollY?: number;
  allowStudentControl?: boolean;
}

export interface SyncControlPayload {
  allowStudentControl: boolean;
}

export interface SyncEnvelope<TType extends string = string, TPayload = any> {
  type: TType;
  payload: TPayload;
  senderId: string;
  role: SyncRole;
  timestamp: number; // UTC Epoch milliseconds
}

export type ClassroomSyncEnvelope<T = any> = SyncEnvelope<string, T>;

export interface SyncTransport {
  sendAppMessage: (data: any, to?: string) => Promise<any> | void;
}

export interface ClassroomSyncState {
  materialId: string | null;
  sectionIndex: number;
  activeTab: CurriculumTabId;
  page: number;
  scrollOffset: number;
  scrollY: number;
  highlightedVocabIndex: number | null;
  activeHighlights: SyncHighlightPayload[];
  allowStudentControl: boolean;
  followTutor: boolean;
  hasUnseenTutorUpdate: boolean;
  latestTutorState: ClassroomSyncState | null;
}

export type ClassroomState = ClassroomSyncState;

export interface SyncEventNotification {
  source: "local" | "remote";
  type: string;
  envelope?: SyncEnvelope;
  snapBack?: boolean;
}

export interface ClassroomSyncOptions {
  role: SyncRole;
  senderId?: string;
  initialMaterialId?: string | null;
  initialSectionIndex?: number;
  initialTab?: CurriculumTabId;
  initialFollowTutor?: boolean;
  initialAllowStudentControl?: boolean;
  allowStudentControl?: boolean;
  transport?: SyncTransport | null;
  now?: () => number;
  scrollThrottleMs?: number;
}

export const TAB_MAP: Record<number, CurriculumTabId> = {
  0: "article",
  1: "vocab",
  2: "questions",
};

export const REVERSE_TAB_MAP: Record<CurriculumTabId, number> = {
  article: 0,
  vocab: 1,
  questions: 2,
};

const VALID_MESSAGE_TYPES: readonly string[] = [
  "SYNC_TAB",
  "SYNC_PAGE",
  "SYNC_SCROLL",
  "SYNC_HIGHLIGHT",
  "CLASSROOM_MATERIAL_SYNC",
  "SYNC_CONTROL",
];

/**
 * Validates whether a raw object conforms to the canonical protocol envelope schema.
 */
export function isValidEnvelope(raw: unknown): raw is SyncEnvelope {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return false;
  }

  // Handle Daily event wrapper if provided: { data: envelope, fromId: ... }
  const data: any = "data" in raw && (raw as any).data && typeof (raw as any).data === "object"
    ? (raw as any).data
    : raw;

  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return false;
  }

  if (typeof data.type !== "string" || !VALID_MESSAGE_TYPES.includes(data.type)) {
    return false;
  }

  if (typeof data.payload !== "object" || data.payload === null || Array.isArray(data.payload)) {
    return false;
  }

  if (typeof data.senderId !== "string" || data.senderId.trim().length === 0) {
    return false;
  }

  if (data.role !== "teacher" && data.role !== "student") {
    return false;
  }

  if (
    typeof data.timestamp !== "number" ||
    !Number.isFinite(data.timestamp) ||
    data.timestamp <= 0
  ) {
    return false;
  }

  return true;
}

/**
 * Mock transport helper for testing WebRTC DataChannel message transmission.
 */
export class MockSyncTransport implements SyncTransport {
  public sentMessages: { data: any; to?: string }[] = [];
  public peer: MockSyncTransport | null = null;
  public onMessage?: (data: any) => void;

  public sendAppMessage(data: any, to?: string): void {
    this.sentMessages.push({ data, to });
    if (this.peer && this.peer.onMessage) {
      this.peer.onMessage(data);
    }
  }

  public clear(): void {
    this.sentMessages = [];
  }

  public lastMessage(): any | null {
    return this.sentMessages.length > 0 ? this.sentMessages[this.sentMessages.length - 1].data : null;
  }

  public get lastSent(): any | null {
    return this.lastMessage();
  }
}

export const MockTransport = MockSyncTransport;

/**
 * Pure TypeScript ClassroomSyncCoordinator
 * Zero DOM or browser dependencies.
 */
export class ClassroomSyncCoordinator {
  private role: SyncRole;
  private senderId: string;
  private state: ClassroomSyncState;
  private cachedTutorState: ClassroomSyncState | null = null;
  private lastTutorTimestamp: number = 0;
  private lastAppliedTimestamp: number = 0;
  private transport: SyncTransport | null = null;
  private now: () => number;
  private isApplyingRemoteUpdate: boolean = false;
  private listeners: Set<(state: ClassroomSyncState, event: SyncEventNotification) => void> = new Set();

  private scrollThrottleMs: number;
  private pendingScrollTimer: any = null;
  private pendingScrollOffset: number | null = null;
  private lastGeneratedTimestamp: number = 0;

  private getMonotonicTimestamp(): number {
    const current = this.now();
    if (current <= this.lastGeneratedTimestamp) {
      this.lastGeneratedTimestamp += 1;
    } else {
      this.lastGeneratedTimestamp = current;
    }
    return this.lastGeneratedTimestamp;
  }

  constructor(options: ClassroomSyncOptions) {
    this.role = options.role;
    this.senderId = options.senderId || (options.role === "teacher" ? "teacher-local" : "student-local");
    this.now = options.now || (() => Date.now());
    this.scrollThrottleMs = options.scrollThrottleMs ?? 50;
    this.transport = options.transport ?? null;

    const initialSection = options.initialSectionIndex ?? 0;
    const initialTab = options.initialTab ?? TAB_MAP[initialSection] ?? "article";
    const initialControl = options.initialAllowStudentControl ?? options.allowStudentControl ?? false;

    this.state = {
      materialId: options.initialMaterialId ?? null,
      sectionIndex: initialSection,
      activeTab: initialTab,
      page: 1,
      scrollOffset: 0.0,
      scrollY: 0.0,
      highlightedVocabIndex: null,
      activeHighlights: [],
      allowStudentControl: initialControl,
      followTutor: options.role === "student" ? (options.initialFollowTutor ?? true) : false,
      hasUnseenTutorUpdate: false,
      latestTutorState: null,
    };
  }

  // --- Transport Binding ---
  public setTransport(transport: SyncTransport | null): void {
    this.transport = transport;
  }

  public getSenderId(): string {
    return this.senderId;
  }

  public getRole(): SyncRole {
    return this.role;
  }

  public isFollowTutor(): boolean {
    return this.state.followTutor;
  }

  public isStudentControlAllowed(): boolean {
    return this.state.allowStudentControl;
  }

  public getState(): Readonly<ClassroomSyncState> {
    return {
      ...this.state,
      activeHighlights: [...this.state.activeHighlights],
      latestTutorState: this.cachedTutorState ? { ...this.cachedTutorState } : null,
    };
  }

  public getCachedTutorState(): Readonly<ClassroomSyncState> | null {
    return this.cachedTutorState ? { ...this.cachedTutorState } : null;
  }

  public getLatestTutorState(): Readonly<ClassroomSyncState> | null {
    return this.getCachedTutorState();
  }

  // --- State Subscription ---
  public subscribe(
    callback: (state: ClassroomSyncState, event: SyncEventNotification) => void
  ): () => void {
    this.listeners.add(callback);
    return () => {
      this.listeners.delete(callback);
    };
  }

  private notify(event: SyncEventNotification): void {
    const currentState = this.getState();
    for (const listener of this.listeners) {
      try {
        listener(currentState, event);
      } catch (e) {
        console.error("Error in classroomSync listener:", e);
      }
    }
  }

  // --- Follow Tutor State Machine ---
  public setFollowTutor(enabled: boolean): void {
    if (this.role !== "student") return;
    this.state.followTutor = enabled;

    if (enabled && this.cachedTutorState) {
      // Snap back immediately to tutor's cached state
      this.state.materialId = this.cachedTutorState.materialId;
      this.state.sectionIndex = this.cachedTutorState.sectionIndex;
      this.state.activeTab = this.cachedTutorState.activeTab;
      this.state.page = this.cachedTutorState.page;
      this.state.scrollOffset = this.cachedTutorState.scrollOffset;
      this.state.scrollY = this.cachedTutorState.scrollY;
      this.state.highlightedVocabIndex = this.cachedTutorState.highlightedVocabIndex;
      this.state.activeHighlights = [...this.cachedTutorState.activeHighlights];
      this.state.hasUnseenTutorUpdate = false;
      this.notify({ source: "local", type: "SNAP_BACK", snapBack: true });
      return;
    }

    this.notify({ source: "local", type: "FOLLOW_TUTOR_TOGGLE" });
  }

  // --- Interactive Control Mode (Teacher Only) ---
  public setStudentControlAllowed(allowed: boolean): void {
    if (this.role !== "teacher") return;
    this.state.allowStudentControl = allowed;

    this.broadcastEnvelope({
      type: "SYNC_CONTROL",
      payload: { allowStudentControl: allowed },
      senderId: this.senderId,
      role: "teacher",
      timestamp: this.getMonotonicTimestamp(),
    });

    this.notify({ source: "local", type: "SYNC_CONTROL" });
  }

  public setAllowStudentControl(allowed: boolean): void {
    this.setStudentControlAllowed(allowed);
  }

  // --- Tab & Section Synchronization ---
  public syncTab(tabOrIndex: CurriculumTabId | number): void {
    let tab: CurriculumTabId;
    let index: number;

    if (typeof tabOrIndex === "number") {
      index = tabOrIndex;
      tab = TAB_MAP[index] ?? "article";
    } else {
      tab = tabOrIndex;
      index = REVERSE_TAB_MAP[tab] ?? 0;
    }

    if (this.role === "student" && !this.state.allowStudentControl) {
      if (!this.state.followTutor) {
        // Independent review mode
        this.state.sectionIndex = index;
        this.state.activeTab = tab;
        this.state.highlightedVocabIndex = null;
        this.notify({ source: "local", type: "SYNC_TAB" });
      }
      return;
    }

    if (!this.canInitiateAction()) return;

    if (this.state.sectionIndex === index && this.state.activeTab === tab) {
      return;
    }

    this.state.sectionIndex = index;
    this.state.activeTab = tab;
    this.state.highlightedVocabIndex = null;

    if (!this.isApplyingRemoteUpdate && (this.role === "teacher" || (this.role === "student" && this.state.allowStudentControl))) {
      this.broadcastEnvelope({
        type: "SYNC_TAB",
        payload: { tab, tabIndex: index },
        senderId: this.senderId,
        role: this.role,
        timestamp: this.getMonotonicTimestamp(),
      });
    }

    this.notify({ source: "local", type: "SYNC_TAB" });
  }

  public switchTab(tabOrIndex: CurriculumTabId | number): void {
    this.syncTab(tabOrIndex);
  }

  // --- Page Synchronization ---
  public syncPage(page: number, totalPages?: number, materialId?: string | null): void {
    if (page < 0) return;

    if (this.role === "student" && !this.state.allowStudentControl) {
      if (!this.state.followTutor) {
        this.state.page = page;
        this.state.sectionIndex = page;
        if (materialId !== undefined) {
          this.state.materialId = materialId;
        }
        this.notify({ source: "local", type: "SYNC_PAGE" });
      }
      return;
    }

    if (!this.canInitiateAction()) return;

    this.state.page = page;
    this.state.sectionIndex = page;
    if (materialId !== undefined) {
      this.state.materialId = materialId;
    }

    if (!this.isApplyingRemoteUpdate && (this.role === "teacher" || (this.role === "student" && this.state.allowStudentControl))) {
      this.broadcastEnvelope({
        type: "SYNC_PAGE",
        payload: { page, totalPages, materialId: this.state.materialId },
        senderId: this.senderId,
        role: this.role,
        timestamp: this.getMonotonicTimestamp(),
      });
    }

    this.notify({ source: "local", type: "SYNC_PAGE" });
  }

  public navigatePage(page: number, materialId?: string | null): void {
    this.syncPage(page, undefined, materialId);
  }

  // --- Scroll Synchronization (Deadband & Throttle) ---
  public syncScroll(scrollOffset: number, immediate: boolean = false): void {
    if (scrollOffset < 0) return;
    const clamped = Math.max(0.0, Math.min(1.0, scrollOffset));

    if (this.role === "student" && !this.state.allowStudentControl) {
      if (!this.state.followTutor) {
        this.state.scrollOffset = clamped;
        this.state.scrollY = clamped;
        this.notify({ source: "local", type: "SYNC_SCROLL" });
      }
      return;
    }

    if (!this.canInitiateAction()) return;

    if (Math.abs(clamped - this.state.scrollOffset) < 0.005) {
      return; // Inside deadband; avoid redundant traffic
    }

    this.state.scrollOffset = clamped;
    this.state.scrollY = clamped;

    if (this.isApplyingRemoteUpdate) {
      return;
    }

    if (immediate || this.scrollThrottleMs <= 0) {
      this.flushScrollBroadcast(clamped);
    } else {
      this.pendingScrollOffset = clamped;
      if (!this.pendingScrollTimer) {
        this.pendingScrollTimer = setTimeout(() => {
          this.pendingScrollTimer = null;
          if (this.pendingScrollOffset !== null) {
            this.flushScrollBroadcast(this.pendingScrollOffset);
            this.pendingScrollOffset = null;
          }
        }, this.scrollThrottleMs);
      }
    }

    this.notify({ source: "local", type: "SYNC_SCROLL" });
  }

  public scrollTo(scrollY: number, scrollPercentage?: number, immediate: boolean = false): void {
    const target = scrollPercentage !== undefined ? scrollPercentage : (scrollY > 1 ? scrollY / 1000 : scrollY);
    this.syncScroll(target, immediate);
  }

  private flushScrollBroadcast(offset: number): void {
    this.broadcastEnvelope({
      type: "SYNC_SCROLL",
      payload: { scrollOffset: offset, scrollY: offset },
      senderId: this.senderId,
      role: this.role,
      timestamp: this.getMonotonicTimestamp(),
    });
  }

  // --- Highlight Synchronization ---
  public syncHighlight(
    action: HighlightAction,
    options: {
      vocabIndex?: number | null;
      sectionId?: string;
      textRange?: { startOffset: number; endOffset: number; text?: string };
      color?: string;
      highlightId?: string;
    } = {}
  ): void {
    if (this.role === "student" && !this.state.allowStudentControl) {
      if (!this.state.followTutor) {
        if (options.vocabIndex !== undefined) {
          this.state.highlightedVocabIndex = action === "clear" ? null : options.vocabIndex;
          if (action === "set" && options.vocabIndex !== null) {
            this.state.sectionIndex = 1;
            this.state.activeTab = "vocab";
          }
        }
        this.notify({ source: "local", type: "SYNC_HIGHLIGHT" });
      }
      return;
    }

    if (!this.canInitiateAction()) return;

    const payload: SyncHighlightPayload = {
      action,
      highlightId: options.highlightId || `hl-${this.now()}-${Math.random().toString(36).slice(2, 7)}`,
      vocabIndex: options.vocabIndex ?? null,
      sectionId: options.sectionId,
      textRange: options.textRange,
      color: options.color,
      attributedTo: {
        senderId: this.senderId,
        role: this.role,
      },
      timestamp: this.getMonotonicTimestamp(),
    };

    if (options.vocabIndex !== undefined) {
      this.state.highlightedVocabIndex = action === "clear" ? null : options.vocabIndex;
      if (action === "set" && options.vocabIndex !== null) {
        this.state.sectionIndex = 1;
        this.state.activeTab = "vocab";
      }
    }

    if (action === "clear") {
      if (options.highlightId) {
        this.state.activeHighlights = this.state.activeHighlights.filter(
          (h) => h.highlightId !== options.highlightId
        );
      } else {
        this.state.activeHighlights = [];
      }
    } else {
      this.state.activeHighlights.push(payload);
    }

    if (!this.isApplyingRemoteUpdate && (this.role === "teacher" || (this.role === "student" && this.state.allowStudentControl))) {
      this.broadcastEnvelope({
        type: "SYNC_HIGHLIGHT",
        payload,
        senderId: this.senderId,
        role: this.role,
        timestamp: payload.timestamp,
      });
    }

    this.notify({ source: "local", type: "SYNC_HIGHLIGHT" });
  }

  public highlightVocab(vocabIndex: number | null, textSnippet?: string): void {
    this.syncHighlight(vocabIndex === null ? "clear" : "set", { vocabIndex });
  }

  // --- Material Synchronization (Teacher Authoritative) ---
  public syncMaterial(materialId: string | null, sectionIndex: number = 0): void {
    if (this.role !== "teacher") return;

    this.state.materialId = materialId;
    this.state.sectionIndex = sectionIndex;
    this.state.activeTab = TAB_MAP[sectionIndex] ?? "article";
    this.state.highlightedVocabIndex = null;
    this.state.scrollOffset = 0.0;
    this.state.scrollY = 0.0;
    this.state.activeHighlights = [];

    const payload: ClassroomMaterialSyncPayload = {
      materialId,
      sectionIndex,
      activeTab: this.state.activeTab,
      highlightedVocabIndex: null,
      scrollY: 0.0,
      allowStudentControl: this.state.allowStudentControl,
    };

    this.broadcastEnvelope({
      type: "CLASSROOM_MATERIAL_SYNC",
      payload,
      senderId: this.senderId,
      role: "teacher",
      timestamp: this.getMonotonicTimestamp(),
    });

    this.notify({ source: "local", type: "CLASSROOM_MATERIAL_SYNC" });
  }

  public syncFullMaterial(materialId: string | null): void {
    this.syncMaterial(materialId);
  }

  // --- Student Independent Local Actions ---
  public studentNavigateTab(tabOrIndex: CurriculumTabId | number): void {
    if (this.role !== "student") return;
    this.state.followTutor = false;

    let tab: CurriculumTabId;
    let index: number;
    if (typeof tabOrIndex === "number") {
      index = tabOrIndex;
      tab = TAB_MAP[index] ?? "article";
    } else {
      tab = tabOrIndex;
      index = REVERSE_TAB_MAP[tab] ?? 0;
    }

    this.state.sectionIndex = index;
    this.state.activeTab = tab;
    this.state.highlightedVocabIndex = null;
    this.notify({ source: "local", type: "SYNC_TAB" });
  }

  public studentNavigatePage(page: number): void {
    if (this.role !== "student" || page < 0) return;
    this.state.followTutor = false;
    this.state.page = page;
    this.state.sectionIndex = page;
    this.notify({ source: "local", type: "SYNC_PAGE" });
  }

  public studentScrollTo(scrollY: number): void {
    if (this.role !== "student" || scrollY < 0) return;
    this.state.followTutor = false;
    const clamped = Math.max(0.0, Math.min(1.0, scrollY > 1 ? scrollY / 1000 : scrollY));
    this.state.scrollOffset = clamped;
    this.state.scrollY = clamped;
    this.notify({ source: "local", type: "SYNC_SCROLL" });
  }

  public studentHighlightVocab(vocabIndex: number | null): void {
    if (this.role !== "student") return;
    this.state.followTutor = false;
    this.state.highlightedVocabIndex = vocabIndex;
    if (vocabIndex !== null) {
      this.state.sectionIndex = 1;
      this.state.activeTab = "vocab";
    }
    this.notify({ source: "local", type: "SYNC_HIGHLIGHT" });
  }

  // --- Inbound AppMessage Processing ---
  public handleAppMessage(eventOrEnvelope: any, trustedSender?: TrustedSyncSender): boolean {
    const envelope = this.parseEnvelope(eventOrEnvelope, trustedSender);
    if (!envelope) return false;

    // Discard loopback reflection
    if (envelope.senderId === this.senderId) {
      return false;
    }

    // Role Authority Evaluation:
    // Teacher peer rejects student messages unless allowStudentControl is true
    if (this.role === "teacher" && envelope.role === "student") {
      if (!this.state.allowStudentControl) {
        return false;
      }
      // Student cannot emit teacher-only control messages
      if (envelope.type === "SYNC_CONTROL" || envelope.type === "CLASSROOM_MATERIAL_SYNC") {
        return false;
      }
    }

    // Monotonic LWW Timestamp Check
    if (envelope.timestamp <= this.lastAppliedTimestamp) {
      return false; // Stale or duplicate packet
    }

    if (envelope.role === "teacher") {
      if (envelope.timestamp <= this.lastTutorTimestamp) {
        return false;
      }
      this.lastTutorTimestamp = envelope.timestamp;
    }

    this.lastAppliedTimestamp = envelope.timestamp;

    // Apply remote update under re-entrancy suppression guard
    this.isApplyingRemoteUpdate = true;
    let stateChanged = false;

    try {
      stateChanged = this.applyRemoteEnvelope(envelope);
    } finally {
      this.isApplyingRemoteUpdate = false;
    }

    return stateChanged;
  }

  // --- Internal Remote State Application ---
  private applyRemoteEnvelope(envelope: SyncEnvelope): boolean {
    const isTeacherSender = envelope.role === "teacher";

    // Cache tutor position if sender is teacher
    if (isTeacherSender) {
      if (!this.cachedTutorState) {
        this.cachedTutorState = {
          ...this.state,
          activeHighlights: [...this.state.activeHighlights],
        };
      }
      this.updateStateSlice(this.cachedTutorState, envelope);
      this.state.latestTutorState = { ...this.cachedTutorState };
    }

    // Student "Follow Tutor" state machine branch
    if (this.role === "student" && !this.state.followTutor && isTeacherSender) {
      if (envelope.type === "SYNC_CONTROL") {
        // Teacher permission toggle applies immediately even in manual review mode
        this.state.allowStudentControl = !!envelope.payload?.allowStudentControl;
        this.notify({ source: "remote", type: envelope.type, envelope });
        return true;
      }
      // Background tutor caching without modifying student's active view
      this.state.hasUnseenTutorUpdate = true;
      this.notify({ source: "remote", type: "TUTOR_CACHE_UPDATED", envelope });
      return true;
    }

    // Normal direct application
    const changed = this.updateStateSlice(this.state, envelope);
    if (changed) {
      this.notify({ source: "remote", type: envelope.type, envelope });
    }
    return changed;
  }

  private updateStateSlice(target: ClassroomSyncState, envelope: SyncEnvelope): boolean {
    switch (envelope.type) {
      case "CLASSROOM_MATERIAL_SYNC": {
        const p = envelope.payload as ClassroomMaterialSyncPayload;
        target.materialId = p.materialId;
        target.sectionIndex = Number(p.sectionIndex ?? 0);
        target.activeTab = TAB_MAP[target.sectionIndex] ?? "article";
        target.highlightedVocabIndex = p.highlightedVocabIndex ?? null;
        if (p.scrollY !== undefined) {
          target.scrollY = p.scrollY;
          target.scrollOffset = p.scrollY;
        }
        if (p.allowStudentControl !== undefined) {
          target.allowStudentControl = p.allowStudentControl;
        }
        return true;
      }

      case "SYNC_TAB": {
        const p = envelope.payload as SyncTabPayload;
        let index: number;
        let tab: CurriculumTabId;

        if (typeof p.tabIndex === "number") {
          index = p.tabIndex;
          tab = TAB_MAP[index] ?? (p.tab as CurriculumTabId) ?? "article";
        } else {
          tab = (p.tab as CurriculumTabId) ?? "article";
          index = REVERSE_TAB_MAP[tab] ?? 0;
        }

        target.sectionIndex = index;
        target.activeTab = tab;
        target.highlightedVocabIndex = null;
        return true;
      }

      case "SYNC_PAGE": {
        const p = envelope.payload as SyncPagePayload;
        target.page = p.page;
        target.sectionIndex = p.page;
        if (p.materialId !== undefined) {
          target.materialId = p.materialId;
        }
        return true;
      }

      case "SYNC_SCROLL": {
        const p = envelope.payload as SyncScrollPayload;
        const offset = p.scrollOffset ?? p.scrollY ?? 0.0;
        target.scrollOffset = offset;
        target.scrollY = offset;
        return true;
      }

      case "SYNC_HIGHLIGHT": {
        const p = envelope.payload as SyncHighlightPayload;
        if (p.action === "clear") {
          if (p.highlightId) {
            target.activeHighlights = target.activeHighlights.filter((h) => h.highlightId !== p.highlightId);
          } else {
            target.activeHighlights = [];
          }
          if (p.vocabIndex !== undefined) {
            target.highlightedVocabIndex = null;
          }
        } else {
          target.activeHighlights.push(p);
          if (p.vocabIndex !== null && p.vocabIndex !== undefined) {
            target.highlightedVocabIndex = p.vocabIndex;
            target.sectionIndex = 1;
            target.activeTab = "vocab";
          }
        }
        return true;
      }

      case "SYNC_CONTROL": {
        const p = envelope.payload as SyncControlPayload;
        target.allowStudentControl = !!p.allowStudentControl;
        return true;
      }

      default:
        return false;
    }
  }

  // --- Envelope Normalizer ---
  private parseEnvelope(raw: any, trustedSender?: TrustedSyncSender): SyncEnvelope | null {
    if (!raw) return null;
    const data = raw.data ? raw.data : raw;

    // Daily assigns the top-level fromId. Wrapped provider messages must be
    // bound to participant metadata supplied by the Daily SDK, never to role
    // or sender fields controlled by the remote peer.
    if (raw.fromId && !trustedSender) return null;
    if (
      trustedSender &&
      (!trustedSender.senderId ||
        (trustedSender.role !== "teacher" && trustedSender.role !== "student") ||
        (raw.fromId && raw.fromId !== trustedSender.senderId))
    ) {
      return null;
    }

    if (typeof data !== "object" || data === null || Array.isArray(data)) return null;

    // Standard envelope structure
    if (data.type && typeof data.timestamp === "number" && Number.isFinite(data.timestamp) && data.timestamp > 0 && data.payload !== undefined && data.payload !== null) {
      if (!VALID_MESSAGE_TYPES.includes(data.type)) return null;
      if (data.role !== "teacher" && data.role !== "student") return null;
      const senderId = String(trustedSender?.senderId || data.senderId || "").trim();
      if (!senderId) return null;
      const role: SyncRole = trustedSender?.role || data.role;

      return {
        type: String(data.type),
        payload: data.payload,
        senderId,
        role,
        timestamp: data.timestamp,
      };
    }

    // Support flat CLASSROOM_MATERIAL_SYNC packets
    if (data.type === "CLASSROOM_MATERIAL_SYNC") {
      if (!trustedSender && data.senderRole !== "teacher" && data.senderRole !== "student") return null;
      const senderId = String(trustedSender?.senderId || data.senderId || "").trim();
      if (!senderId) return null;
      const ts = Number(data.timestamp || this.now());
      if (ts <= 0 || !Number.isFinite(ts)) return null;

      return {
        type: "CLASSROOM_MATERIAL_SYNC",
        payload: {
          materialId: data.materialId ?? null,
          sectionIndex: Number(data.sectionIndex ?? 0),
          highlightedVocabIndex: data.highlightedVocabIndex ?? null,
          allowStudentControl: !!data.allowStudentControl,
        },
        senderId,
        role: trustedSender?.role || data.senderRole,
        timestamp: ts,
      };
    }

    return null;
  }

  // --- Permissions Check ---
  private canInitiateAction(): boolean {
    if (this.role === "teacher") return true;
    return this.state.allowStudentControl;
  }

  // --- Outbound Broadcast Dispatcher ---
  private broadcastEnvelope(envelope: SyncEnvelope): void {
    if (!this.transport) return;
    try {
      this.transport.sendAppMessage(envelope, "*");
    } catch (err) {
      console.warn("ClassroomSyncCoordinator: Failed to broadcast app message:", err);
    }
  }

  // --- Lifecycle Teardown ---
  public destroy(): void {
    if (this.pendingScrollTimer) {
      clearTimeout(this.pendingScrollTimer);
      this.pendingScrollTimer = null;
    }
    this.listeners.clear();
    this.transport = null;
  }
}
