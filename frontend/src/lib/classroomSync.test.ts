import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  ClassroomSyncCoordinator,
  MockSyncTransport,
  isValidEnvelope,
  SyncEnvelope,
  ClassroomSyncState,
} from "./classroomSync";

describe("Milestone 3: Classroom Material Synchronization (Requirement R3)", () => {
  let teacherTransport: MockSyncTransport;
  let studentTransport: MockSyncTransport;
  let teacherCoordinator: ClassroomSyncCoordinator;
  let studentCoordinator: ClassroomSyncCoordinator;

  beforeEach(() => {
    teacherTransport = new MockSyncTransport();
    studentTransport = new MockSyncTransport();

    // Wire simulated WebRTC peer-to-peer transport
    teacherTransport.peer = studentTransport;
    studentTransport.peer = teacherTransport;

    teacherCoordinator = new ClassroomSyncCoordinator({
      role: "teacher",
      senderId: "teacher-peer-1",
      initialMaterialId: "business-negotiations-b2",
      transport: teacherTransport,
      scrollThrottleMs: 0, // Zero throttle for deterministic synchronous unit tests
    });

    studentCoordinator = new ClassroomSyncCoordinator({
      role: "student",
      senderId: "student-peer-1",
      initialMaterialId: "business-negotiations-b2",
      transport: studentTransport,
      scrollThrottleMs: 0,
    });

    teacherTransport.onMessage = (data) => teacherCoordinator.handleAppMessage(data);
    studentTransport.onMessage = (data) => studentCoordinator.handleAppMessage(data);
  });

  // =========================================================================
  // Suite 1: Envelope Validation & Extraction
  // =========================================================================
  describe("Suite 1: Envelope Validation & Extraction", () => {
    it("1.1: Valid envelopes for all 6 protocol message types pass validation", () => {
      const types = [
        "SYNC_TAB",
        "SYNC_PAGE",
        "SYNC_SCROLL",
        "SYNC_HIGHLIGHT",
        "CLASSROOM_MATERIAL_SYNC",
        "SYNC_CONTROL",
      ] as const;

      for (const type of types) {
        const env: SyncEnvelope = {
          type,
          payload: { foo: "bar" },
          senderId: "peer-valid",
          role: "teacher",
          timestamp: 1700000000000,
        };
        assert.equal(isValidEnvelope(env), true, `Expected ${type} to be valid`);
      }
    });

    it("1.2: Rejects non-objects, null, undefined, primitives, and arrays", () => {
      assert.equal(isValidEnvelope(null), false);
      assert.equal(isValidEnvelope(undefined), false);
      assert.equal(isValidEnvelope("hello"), false);
      assert.equal(isValidEnvelope(12345), false);
      assert.equal(isValidEnvelope([]), false);
      assert.equal(isValidEnvelope(true), false);
    });

    it("1.3: Rejects unknown or empty message types", () => {
      assert.equal(
        isValidEnvelope({
          type: "UNKNOWN_TYPE",
          payload: {},
          senderId: "p1",
          role: "teacher",
          timestamp: 100,
        }),
        false
      );
      assert.equal(
        isValidEnvelope({
          type: "",
          payload: {},
          senderId: "p1",
          role: "teacher",
          timestamp: 100,
        }),
        false
      );
    });

    it("1.4: Rejects missing or non-object payloads", () => {
      assert.equal(
        isValidEnvelope({
          type: "SYNC_TAB",
          payload: null,
          senderId: "p1",
          role: "teacher",
          timestamp: 100,
        }),
        false
      );
      assert.equal(
        isValidEnvelope({
          type: "SYNC_TAB",
          payload: "not-an-object",
          senderId: "p1",
          role: "teacher",
          timestamp: 100,
        }),
        false
      );
    });

    it("1.5: Rejects empty or whitespace-only senderId", () => {
      assert.equal(
        isValidEnvelope({
          type: "SYNC_TAB",
          payload: {},
          senderId: "",
          role: "teacher",
          timestamp: 100,
        }),
        false
      );
      assert.equal(
        isValidEnvelope({
          type: "SYNC_TAB",
          payload: {},
          senderId: "   ",
          role: "teacher",
          timestamp: 100,
        }),
        false
      );
    });

    it("1.6: Rejects invalid roles (not 'teacher' or 'student')", () => {
      assert.equal(
        isValidEnvelope({
          type: "SYNC_TAB",
          payload: {},
          senderId: "p1",
          role: "admin" as any,
          timestamp: 100,
        }),
        false
      );
      assert.equal(
        isValidEnvelope({
          type: "SYNC_TAB",
          payload: {},
          senderId: "p1",
          role: "" as any,
          timestamp: 100,
        }),
        false
      );
    });

    it("1.7: Rejects non-numeric, zero, negative, or infinite timestamps", () => {
      const base = {
        type: "SYNC_TAB",
        payload: { tab: "vocab" },
        senderId: "p1",
        role: "teacher",
      };

      assert.equal(isValidEnvelope({ ...base, timestamp: 0 }), false);
      assert.equal(isValidEnvelope({ ...base, timestamp: -500 }), false);
      assert.equal(isValidEnvelope({ ...base, timestamp: NaN }), false);
      assert.equal(isValidEnvelope({ ...base, timestamp: Infinity }), false);
      assert.equal(isValidEnvelope({ ...base, timestamp: "17000000" as any }), false);
    });

    it("1.8: Safely unwraps Daily.co app-message event wrapper", () => {
      const dailyEvent = {
        action: "app-message",
        fromId: "teacher-peer-1",
        data: {
          type: "SYNC_TAB",
          payload: { tab: "questions", tabIndex: 2 },
          senderId: "teacher-peer-1",
          role: "teacher",
          timestamp: 1000,
        },
      };

      assert.equal(isValidEnvelope(dailyEvent), true);
      const handled = studentCoordinator.handleAppMessage(dailyEvent, {
        senderId: "teacher-peer-1",
        role: "teacher",
      });
      assert.equal(handled, true);
      assert.equal(studentCoordinator.getState().activeTab, "questions");
      assert.equal(studentCoordinator.getState().sectionIndex, 2);
    });

    it("1.8b: Uses Daily's authenticated participant role instead of the packet claim", () => {
      const initialMaterialId = teacherCoordinator.getState().materialId;
      const forgedTeacherEvent = {
        action: "app-message",
        fromId: "student-peer-1",
        data: {
          type: "CLASSROOM_MATERIAL_SYNC",
          payload: { materialId: "forged", sectionIndex: 2 },
          senderId: "pretend-teacher",
          role: "teacher",
          timestamp: 1100,
        },
      };

      const handled = teacherCoordinator.handleAppMessage(forgedTeacherEvent, {
        senderId: "student-peer-1",
        role: "student",
      });

      assert.equal(handled, false);
      assert.equal(teacherCoordinator.getState().materialId, initialMaterialId);
    });

    it("1.9: Parses legacy flat CLASSROOM_MATERIAL_SYNC packet format", () => {
      const flatPacket = {
        type: "CLASSROOM_MATERIAL_SYNC",
        materialId: "travel-english-a2",
        sectionIndex: 1,
        highlightedVocabIndex: 3,
        senderRole: "teacher",
        senderId: "teacher-peer-1",
        timestamp: 1200,
      };

      const handled = studentCoordinator.handleAppMessage(flatPacket);
      assert.equal(handled, true);
      assert.equal(studentCoordinator.getState().materialId, "travel-english-a2");
      assert.equal(studentCoordinator.getState().sectionIndex, 1);
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
      assert.equal(studentCoordinator.getState().highlightedVocabIndex, 3);
    });
  });

  // =========================================================================
  // Suite 2: Monotonic LWW Timestamp Ordering
  // =========================================================================
  describe("Suite 2: Monotonic LWW Timestamp Ordering", () => {
    it("2.1: Accepts strictly newer packets (t = 200 after t = 100)", () => {
      const p1: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "vocab", tabIndex: 1 },
        senderId: "teacher-peer-1",
        role: "teacher",
        timestamp: 100,
      };
      const p2: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "questions", tabIndex: 2 },
        senderId: "teacher-peer-1",
        role: "teacher",
        timestamp: 200,
      };

      assert.equal(studentCoordinator.handleAppMessage(p1), true);
      assert.equal(studentCoordinator.getState().activeTab, "vocab");

      assert.equal(studentCoordinator.handleAppMessage(p2), true);
      assert.equal(studentCoordinator.getState().activeTab, "questions");
    });

    it("2.2: Discards stale packets (t = 50 after t = 100)", () => {
      const p1: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "vocab", tabIndex: 1 },
        senderId: "teacher-peer-1",
        role: "teacher",
        timestamp: 100,
      };
      const stale: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "article", tabIndex: 0 },
        senderId: "teacher-peer-1",
        role: "teacher",
        timestamp: 50,
      };

      assert.equal(studentCoordinator.handleAppMessage(p1), true);
      assert.equal(studentCoordinator.handleAppMessage(stale), false);
      // State must remain on vocab
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
    });

    it("2.3: Discards duplicate packets with identical timestamp (t = 100 after t = 100)", () => {
      const p1: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "vocab", tabIndex: 1 },
        senderId: "teacher-peer-1",
        role: "teacher",
        timestamp: 100,
      };
      const dup: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "questions", tabIndex: 2 },
        senderId: "teacher-peer-1",
        role: "teacher",
        timestamp: 100,
      };

      assert.equal(studentCoordinator.handleAppMessage(p1), true);
      assert.equal(studentCoordinator.handleAppMessage(dup), false);
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
    });

    it("2.4: Out-of-order burst delivery ([100, 400, 200, 300, 500]) applies only 100, 400, 500", () => {
      const burst = [
        { ts: 100, tab: "article" as const, idx: 0 },
        { ts: 400, tab: "questions" as const, idx: 2 },
        { ts: 200, tab: "vocab" as const, idx: 1 },
        { ts: 300, tab: "article" as const, idx: 0 },
        { ts: 500, tab: "vocab" as const, idx: 1 },
      ];

      const results = burst.map((b) =>
        studentCoordinator.handleAppMessage({
          type: "SYNC_TAB",
          payload: { tab: b.tab, tabIndex: b.idx },
          senderId: "teacher-peer-1",
          role: "teacher",
          timestamp: b.ts,
        })
      );

      assert.deepEqual(results, [true, true, false, false, true]);
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
      assert.equal(studentCoordinator.getState().sectionIndex, 1);
    });
  });

  // =========================================================================
  // Suite 3: Echo Suppression & Loopback Filtering
  // =========================================================================
  describe("Suite 3: Echo Suppression & Loopback Filtering", () => {
    it("3.1: Discards incoming envelope if senderId matches own senderId", () => {
      const loopback: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "vocab", tabIndex: 1 },
        senderId: teacherCoordinator.getSenderId(),
        role: "teacher",
        timestamp: 500,
      };

      const result = teacherCoordinator.handleAppMessage(loopback);
      assert.equal(result, false);
      assert.equal(teacherCoordinator.getState().activeTab, "article");
    });

    it("3.2: Applying inbound remote message produces ZERO outbound sendAppMessage calls", () => {
      studentTransport.clear();

      const incoming: SyncEnvelope = {
        type: "SYNC_PAGE",
        payload: { page: 3 },
        senderId: "teacher-peer-1",
        role: "teacher",
        timestamp: 600,
      };

      const handled = studentCoordinator.handleAppMessage(incoming);
      assert.equal(handled, true);
      assert.equal(studentCoordinator.getState().page, 3);
      // Ensure student transport never transmitted an echo
      assert.equal(studentTransport.sentMessages.length, 0);
    });

    it("3.3: Multiple consecutive inbound packets produce zero outbound traffic across transport", () => {
      studentTransport.clear();

      for (let i = 1; i <= 5; i++) {
        studentCoordinator.handleAppMessage({
          type: "SYNC_SCROLL",
          payload: { scrollOffset: i * 0.1 },
          senderId: "teacher-peer-1",
          role: "teacher",
          timestamp: 700 + i,
        });
      }

      assert.equal(studentTransport.sentMessages.length, 0);
      assert.equal(studentCoordinator.getState().scrollOffset, 0.5);
    });

    it("3.4: Local teacher actions trigger outbound broadcasts", () => {
      teacherTransport.clear();
      teacherCoordinator.syncTab("questions");

      assert.equal(teacherTransport.sentMessages.length, 1);
      const msg = teacherTransport.lastMessage();
      assert.equal(msg.type, "SYNC_TAB");
      assert.equal(msg.payload.tab, "questions");
      assert.equal(msg.role, "teacher");
    });
  });

  // =========================================================================
  // Suite 4: Role-Based Authority & Interactive Control Mode
  // =========================================================================
  describe("Suite 4: Role-Based Authority & Interactive Control Mode", () => {
    it("4.1: Teacher actions force-sync student view when followTutor is true", () => {
      assert.equal(studentCoordinator.isFollowTutor(), true);

      teacherCoordinator.syncTab("vocab");

      assert.equal(studentCoordinator.getState().activeTab, "vocab");
      assert.equal(studentCoordinator.getState().sectionIndex, 1);
    });

    it("4.2: Student packets are dropped by teacher when allowStudentControl is false", () => {
      assert.equal(teacherCoordinator.isStudentControlAllowed(), false);

      const studentAction: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "questions", tabIndex: 2 },
        senderId: "student-peer-1",
        role: "student",
        timestamp: 800,
      };

      const accepted = teacherCoordinator.handleAppMessage(studentAction);
      assert.equal(accepted, false);
      assert.equal(teacherCoordinator.getState().activeTab, "article");
    });

    it("4.3: Student packets are accepted and applied by teacher when allowStudentControl is true", () => {
      teacherCoordinator.setStudentControlAllowed(true);
      assert.equal(teacherCoordinator.isStudentControlAllowed(), true);

      const studentAction: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "questions", tabIndex: 2 },
        senderId: "student-peer-1",
        role: "student",
        timestamp: 900,
      };

      const accepted = teacherCoordinator.handleAppMessage(studentAction);
      assert.equal(accepted, true);
      assert.equal(teacherCoordinator.getState().activeTab, "questions");
    });

    it("4.4: Teacher toggling setStudentControlAllowed broadcasts SYNC_CONTROL", () => {
      teacherTransport.clear();
      teacherCoordinator.setStudentControlAllowed(true);

      const last = teacherTransport.lastMessage();
      assert.equal(last.type, "SYNC_CONTROL");
      assert.equal(last.payload.allowStudentControl, true);
      assert.equal(studentCoordinator.isStudentControlAllowed(), true);
    });

    it("4.5: Student cannot broadcast or apply SYNC_CONTROL or CLASSROOM_MATERIAL_SYNC even if student control is enabled", () => {
      teacherCoordinator.setStudentControlAllowed(true);

      // Student attempts to switch material
      const studentMaterialSync: SyncEnvelope = {
        type: "CLASSROOM_MATERIAL_SYNC",
        payload: {
          materialId: "rogue-material-id",
          sectionIndex: 0,
          highlightedVocabIndex: null,
        },
        senderId: "student-peer-1",
        role: "student",
        timestamp: 1000,
      };

      const accepted = teacherCoordinator.handleAppMessage(studentMaterialSync);
      assert.equal(accepted, false);
      assert.notEqual(teacherCoordinator.getState().materialId, "rogue-material-id");
    });
  });

  // =========================================================================
  // Suite 5: "Follow Tutor" State Machine
  // =========================================================================
  describe("Suite 5: 'Follow Tutor' State Machine", () => {
    it("5.1: Student starts with followTutor === true by default", () => {
      assert.equal(studentCoordinator.isFollowTutor(), true);
    });

    it("5.2: Inbound teacher packets immediately update student view when followTutor === true", () => {
      teacherCoordinator.syncTab("questions");
      assert.equal(studentCoordinator.getState().activeTab, "questions");
    });

    it("5.3: Disabling follow tutor allows independent student review without altering teacher view", () => {
      studentCoordinator.setFollowTutor(false);
      assert.equal(studentCoordinator.isFollowTutor(), false);

      studentCoordinator.studentNavigateTab("vocab");
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
      // Teacher remains on initial article tab
      assert.equal(teacherCoordinator.getState().activeTab, "article");
    });

    it("5.4: While followTutor is false, teacher moves update cached state while student active view stays undisturbed", () => {
      studentCoordinator.setFollowTutor(false);
      studentCoordinator.studentNavigateTab("article");

      // Teacher advances to questions
      teacherCoordinator.syncTab("questions");

      // Student active view stays on article!
      assert.equal(studentCoordinator.getState().activeTab, "article");
      assert.equal(studentCoordinator.getState().hasUnseenTutorUpdate, true);

      // Tutor's current position is cached
      const cached = studentCoordinator.getCachedTutorState();
      assert.ok(cached);
      assert.equal(cached.activeTab, "questions");
    });

    it("5.5: Re-enabling follow tutor immediately snaps student view to cached tutor state", () => {
      studentCoordinator.setFollowTutor(false);
      studentCoordinator.studentNavigateTab("article");

      // Teacher moves to questions and highlights vocab 2
      teacherCoordinator.syncTab("vocab");
      teacherCoordinator.highlightVocab(2);

      assert.equal(studentCoordinator.getState().activeTab, "article");

      // Snap back to tutor
      studentCoordinator.setFollowTutor(true);

      assert.equal(studentCoordinator.isFollowTutor(), true);
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
      assert.equal(studentCoordinator.getState().highlightedVocabIndex, 2);
      assert.equal(studentCoordinator.getState().hasUnseenTutorUpdate, false);
    });

    it("5.6: Re-enabling follow tutor before any teacher packet arrived preserves student view safely", () => {
      const freshStudent = new ClassroomSyncCoordinator({
        role: "student",
        initialTab: "article",
        initialFollowTutor: false,
      });

      freshStudent.studentNavigateTab("questions");
      freshStudent.setFollowTutor(true);

      assert.equal(freshStudent.isFollowTutor(), true);
      assert.equal(freshStudent.getState().activeTab, "questions");
    });
  });

  // =========================================================================
  // Suite 6: Scroll Normalization, Deadband & Throttling
  // =========================================================================
  describe("Suite 6: Scroll Normalization, Deadband & Throttling", () => {
    it("6.1: Clamps scroll offset to normalized range [0.0, 1.0]", () => {
      teacherCoordinator.syncScroll(-0.5, true);
      assert.equal(teacherCoordinator.getState().scrollOffset, 0.0);

      teacherCoordinator.syncScroll(1.8, true);
      assert.equal(teacherCoordinator.getState().scrollOffset, 1.0);
    });

    it("6.2: Suppresses scroll broadcasts when offset change is within deadband (< 0.005)", () => {
      teacherTransport.clear();
      teacherCoordinator.syncScroll(0.5, true);
      assert.equal(teacherTransport.sentMessages.length, 1);

      teacherTransport.clear();
      // Delta is 0.002 (< 0.005)
      teacherCoordinator.syncScroll(0.502, true);
      assert.equal(teacherTransport.sentMessages.length, 0);

      // Delta is 0.01 (> 0.005)
      teacherCoordinator.syncScroll(0.512, true);
      assert.equal(teacherTransport.sentMessages.length, 1);
    });

    it("6.3: Throttles rapid successive scroll events with trailing-edge timer", async () => {
      const throttledTeacher = new ClassroomSyncCoordinator({
        role: "teacher",
        transport: teacherTransport,
        scrollThrottleMs: 50,
      });

      teacherTransport.clear();
      throttledTeacher.syncScroll(0.1);
      throttledTeacher.syncScroll(0.2);
      throttledTeacher.syncScroll(0.3);

      // Immediately, zero messages sent due to throttle timer
      assert.equal(teacherTransport.sentMessages.length, 0);

      // Wait 60ms for trailing-edge timer to flush
      await new Promise((resolve) => setTimeout(resolve, 60));

      assert.equal(teacherTransport.sentMessages.length, 1);
      assert.equal(teacherTransport.lastMessage().payload.scrollOffset, 0.3);
      throttledTeacher.destroy();
    });

    it("6.4: Immediate scroll bypasses throttling and broadcasts immediately", () => {
      const throttledTeacher = new ClassroomSyncCoordinator({
        role: "teacher",
        transport: teacherTransport,
        scrollThrottleMs: 100,
      });

      teacherTransport.clear();
      throttledTeacher.syncScroll(0.75, true);

      assert.equal(teacherTransport.sentMessages.length, 1);
      assert.equal(teacherTransport.lastMessage().payload.scrollOffset, 0.75);
      throttledTeacher.destroy();
    });
  });

  // =========================================================================
  // Suite 7: Tab & Section Synchronization
  // =========================================================================
  describe("Suite 7: Tab & Section Synchronization", () => {
    it("7.1: syncTab updates sectionIndex and activeTab for string tab names", () => {
      teacherCoordinator.syncTab("vocab");
      assert.equal(teacherCoordinator.getState().activeTab, "vocab");
      assert.equal(teacherCoordinator.getState().sectionIndex, 1);

      teacherCoordinator.syncTab("questions");
      assert.equal(teacherCoordinator.getState().activeTab, "questions");
      assert.equal(teacherCoordinator.getState().sectionIndex, 2);

      teacherCoordinator.syncTab("article");
      assert.equal(teacherCoordinator.getState().activeTab, "article");
      assert.equal(teacherCoordinator.getState().sectionIndex, 0);
    });

    it("7.2: syncTab updates correctly for numeric indices (0, 1, 2)", () => {
      teacherCoordinator.syncTab(1);
      assert.equal(teacherCoordinator.getState().activeTab, "vocab");
      assert.equal(teacherCoordinator.getState().sectionIndex, 1);

      teacherCoordinator.syncTab(2);
      assert.equal(teacherCoordinator.getState().activeTab, "questions");
      assert.equal(teacherCoordinator.getState().sectionIndex, 2);

      teacherCoordinator.syncTab(0);
      assert.equal(teacherCoordinator.getState().activeTab, "article");
      assert.equal(teacherCoordinator.getState().sectionIndex, 0);
    });

    it("7.3: Redundant tab switch to same tab is a no-op", () => {
      teacherCoordinator.syncTab("vocab");
      teacherTransport.clear();

      teacherCoordinator.syncTab("vocab");
      assert.equal(teacherTransport.sentMessages.length, 0);
    });

    it("7.4: Switching tab clears highlightedVocabIndex back to null", () => {
      teacherCoordinator.highlightVocab(3);
      assert.equal(teacherCoordinator.getState().highlightedVocabIndex, 3);

      teacherCoordinator.syncTab("questions");
      assert.equal(teacherCoordinator.getState().highlightedVocabIndex, null);
    });
  });

  // =========================================================================
  // Suite 8: Vocabulary Card Highlight Attribution & Clearing
  // =========================================================================
  describe("Suite 8: Vocabulary Card Highlight Attribution & Clearing", () => {
    it("8.1: Setting highlight attaches sender attribution, timestamp, and sets highlightedVocabIndex", () => {
      teacherCoordinator.highlightVocab(4);

      assert.equal(teacherCoordinator.getState().highlightedVocabIndex, 4);
      assert.equal(studentCoordinator.getState().highlightedVocabIndex, 4);

      const highlights = teacherCoordinator.getState().activeHighlights;
      assert.equal(highlights.length, 1);
      assert.equal(highlights[0].vocabIndex, 4);
      assert.equal(highlights[0].attributedTo.role, "teacher");
      assert.equal(highlights[0].attributedTo.senderId, "teacher-peer-1");
    });

    it("8.2: Setting vocab highlight automatically switches active tab to 'vocab'", () => {
      teacherCoordinator.syncTab("questions");
      assert.equal(teacherCoordinator.getState().activeTab, "questions");

      teacherCoordinator.highlightVocab(1);
      assert.equal(teacherCoordinator.getState().activeTab, "vocab");
      assert.equal(teacherCoordinator.getState().sectionIndex, 1);
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
    });

    it("8.3: Clearing highlight by highlightId removes specific highlight from activeHighlights", () => {
      teacherCoordinator.syncHighlight("set", { vocabIndex: 0, highlightId: "hl-1" });
      teacherCoordinator.syncHighlight("set", { vocabIndex: 1, highlightId: "hl-2" });

      assert.equal(teacherCoordinator.getState().activeHighlights.length, 2);

      teacherCoordinator.syncHighlight("clear", { highlightId: "hl-1" });
      const remaining = teacherCoordinator.getState().activeHighlights;
      assert.equal(remaining.length, 1);
      assert.equal(remaining[0].highlightId, "hl-2");
    });

    it("8.4: Calling highlightVocab(null) clears highlightedVocabIndex to null", () => {
      teacherCoordinator.highlightVocab(2);
      assert.equal(studentCoordinator.getState().highlightedVocabIndex, 2);

      teacherCoordinator.highlightVocab(null);
      assert.equal(teacherCoordinator.getState().highlightedVocabIndex, null);
      assert.equal(studentCoordinator.getState().highlightedVocabIndex, null);
    });
  });

  // =========================================================================
  // Suite 9: Peer-to-Peer Integration (Simulated WebRTC DataChannel)
  // =========================================================================
  describe("Suite 9: Peer-to-Peer Integration (Simulated WebRTC DataChannel)", () => {
    it("9.1: Two coordinators connected via MockSyncTransport exchange updates seamlessly", () => {
      teacherCoordinator.syncTab("questions");
      assert.equal(studentCoordinator.getState().activeTab, "questions");

      teacherCoordinator.syncPage(4);
      assert.equal(studentCoordinator.getState().page, 4);

      teacherCoordinator.syncScroll(0.8, true);
      assert.equal(studentCoordinator.getState().scrollOffset, 0.8);
    });

    it("9.2: Teacher material change synchronizes student view and resets scroll and vocabulary focus", () => {
      teacherCoordinator.syncScroll(0.9, true);
      teacherCoordinator.highlightVocab(1);

      teacherCoordinator.syncMaterial("advanced-idioms-c1", 0);

      const stState = studentCoordinator.getState();
      assert.equal(stState.materialId, "advanced-idioms-c1");
      assert.equal(stState.sectionIndex, 0);
      assert.equal(stState.activeTab, "article");
      assert.equal(stState.scrollOffset, 0.0);
      assert.equal(stState.highlightedVocabIndex, null);
    });

    it("9.3: Full workflow: Student toggles follow off, browses independently, tutor advances, student toggles follow on and snaps back", () => {
      // Step 1: Follow tutor off
      studentCoordinator.setFollowTutor(false);

      // Step 2: Student browses questions
      studentCoordinator.studentNavigateTab("questions");
      assert.equal(studentCoordinator.getState().activeTab, "questions");
      assert.equal(teacherCoordinator.getState().activeTab, "article");

      // Step 3: Tutor moves to vocab section and highlights item 3
      teacherCoordinator.syncTab("vocab");
      teacherCoordinator.highlightVocab(3);

      // Step 4: Student view remains on questions
      assert.equal(studentCoordinator.getState().activeTab, "questions");
      assert.equal(studentCoordinator.getState().hasUnseenTutorUpdate, true);

      // Step 5: Student snaps back
      studentCoordinator.setFollowTutor(true);
      assert.equal(studentCoordinator.getState().activeTab, "vocab");
      assert.equal(studentCoordinator.getState().highlightedVocabIndex, 3);
      assert.equal(studentCoordinator.getState().hasUnseenTutorUpdate, false);
    });
  });
});
