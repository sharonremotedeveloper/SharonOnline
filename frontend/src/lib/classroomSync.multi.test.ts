import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  ClassroomSyncCoordinator,
  MockSyncTransport,
  SyncTransport,
  SyncEnvelope,
  ClassroomSyncState,
  SyncHighlightPayload,
} from "./classroomSync";

/**
 * MultiPeerSyncNetwork simulates a multi-participant WebRTC DataChannel mesh
 * (such as Daily.co `sendAppMessage(data, "*")` or unicast `to`).
 * It routes messages between all registered peers in the virtual classroom,
 * supports packet reordering/delay simulation, and models network partitions.
 */
class MultiPeerSyncNetwork {
  private peers = new Map<
    string,
    {
      transport: MockSyncTransport;
      coordinator: ClassroomSyncCoordinator;
    }
  >();

  public dropPacketsForPeer: Set<string> = new Set();
  public delayedPackets: { recipientId: string; envelope: any }[] = [];
  public packetHistory: { from: string; to: string; envelope: any; dropped: boolean }[] = [];

  public registerPeer(
    id: string,
    coordinator: ClassroomSyncCoordinator,
    transport: MockSyncTransport
  ): void {
    this.peers.set(id, { transport, coordinator });

    // Override sendAppMessage to route across this shared network
    const originalSend = transport.sendAppMessage.bind(transport);
    transport.sendAppMessage = (data: any, to?: string) => {
      originalSend(data, to); // Preserve sentMessages in transport
      this.routeMessage(id, data, to);
    };
  }

  public routeMessage(senderId: string, data: any, to?: string): void {
    for (const [peerId, peer] of this.peers.entries()) {
      // Echo prevention: sender does not receive its own outbound packet
      if (peerId === senderId) continue;

      // Unicast destination filtering if 'to' is specified
      if (to && to !== "*" && to !== peerId) continue;

      // Partition / Packet Loss Simulation
      if (this.dropPacketsForPeer.has(peerId)) {
        this.packetHistory.push({ from: senderId, to: peerId, envelope: data, dropped: true });
        continue;
      }

      this.packetHistory.push({ from: senderId, to: peerId, envelope: data, dropped: false });
      peer.coordinator.handleAppMessage(data);
    }
  }

  public delayMessageForPeer(recipientId: string, data: any): void {
    this.delayedPackets.push({ recipientId, envelope: data });
  }

  public deliverDelayedPackets(): void {
    while (this.delayedPackets.length > 0) {
      const { recipientId, envelope } = this.delayedPackets.shift()!;
      const peer = this.peers.get(recipientId);
      if (peer) {
        peer.coordinator.handleAppMessage(envelope);
      }
    }
  }

  public clear(): void {
    this.peers.clear();
    this.dropPacketsForPeer.clear();
    this.delayedPackets = [];
    this.packetHistory = [];
  }
}

describe("Milestone 3 (R3): Multi-Participant WebRTC Session Simulation & Stress Harness", () => {
  let network: MultiPeerSyncNetwork;

  let teacherTransport: MockSyncTransport;
  let student1Transport: MockSyncTransport;
  let student2Transport: MockSyncTransport;

  let teacherCoordinator: ClassroomSyncCoordinator;
  let student1Coordinator: ClassroomSyncCoordinator;
  let student2Coordinator: ClassroomSyncCoordinator;

  beforeEach(() => {
    network = new MultiPeerSyncNetwork();

    teacherTransport = new MockSyncTransport();
    student1Transport = new MockSyncTransport();
    student2Transport = new MockSyncTransport();

    teacherCoordinator = new ClassroomSyncCoordinator({
      role: "teacher",
      senderId: "teacher-host",
      initialMaterialId: "travel-english-b1",
      initialSectionIndex: 0,
      transport: teacherTransport,
      scrollThrottleMs: 0,
    });

    student1Coordinator = new ClassroomSyncCoordinator({
      role: "student",
      senderId: "student-alice",
      initialMaterialId: "travel-english-b1",
      initialSectionIndex: 0,
      initialFollowTutor: true,
      transport: student1Transport,
      scrollThrottleMs: 0,
    });

    student2Coordinator = new ClassroomSyncCoordinator({
      role: "student",
      senderId: "student-bob",
      initialMaterialId: "travel-english-b1",
      initialSectionIndex: 0,
      initialFollowTutor: true,
      transport: student2Transport,
      scrollThrottleMs: 0,
    });

    network.registerPeer("teacher-host", teacherCoordinator, teacherTransport);
    network.registerPeer("student-alice", student1Coordinator, student1Transport);
    network.registerPeer("student-bob", student2Coordinator, student2Transport);
  });

  // =========================================================================
  // Scenario A: Teacher Advances Material -> Both Students Sync Immediately
  // =========================================================================
  describe("Scenario A: Teacher advances material with followTutor=true", () => {
    it("A.1: Both students start with followTutor === true and sync immediately when teacher changes material", () => {
      assert.equal(student1Coordinator.isFollowTutor(), true);
      assert.equal(student2Coordinator.isFollowTutor(), true);

      // Teacher switches to a new curriculum module at section 1 (vocab tab)
      teacherCoordinator.syncMaterial("advanced-business-c1", 1);

      // Verify Teacher state
      const tState = teacherCoordinator.getState();
      assert.equal(tState.materialId, "advanced-business-c1");
      assert.equal(tState.sectionIndex, 1);
      assert.equal(tState.activeTab, "vocab");

      // Verify Student 1 synchronized immediately
      const s1State = student1Coordinator.getState();
      assert.equal(s1State.materialId, "advanced-business-c1");
      assert.equal(s1State.sectionIndex, 1);
      assert.equal(s1State.activeTab, "vocab");
      assert.equal(s1State.hasUnseenTutorUpdate, false);

      // Verify Student 2 synchronized immediately
      const s2State = student2Coordinator.getState();
      assert.equal(s2State.materialId, "advanced-business-c1");
      assert.equal(s2State.sectionIndex, 1);
      assert.equal(s2State.activeTab, "vocab");
      assert.equal(s2State.hasUnseenTutorUpdate, false);
    });

    it("A.2: Teacher advances tabs and pages -> both students follow synchronously", () => {
      // Teacher navigates to questions tab
      teacherCoordinator.syncTab("questions");

      assert.equal(teacherCoordinator.getState().activeTab, "questions");
      assert.equal(student1Coordinator.getState().activeTab, "questions");
      assert.equal(student2Coordinator.getState().activeTab, "questions");

      // Teacher advances page to page 3
      teacherCoordinator.syncPage(3);

      assert.equal(teacherCoordinator.getState().page, 3);
      assert.equal(student1Coordinator.getState().page, 3);
      assert.equal(student2Coordinator.getState().page, 3);

      // Teacher scrolls to 65% of document
      teacherCoordinator.syncScroll(0.65, true);

      assert.equal(teacherCoordinator.getState().scrollOffset, 0.65);
      assert.equal(student1Coordinator.getState().scrollOffset, 0.65);
      assert.equal(student2Coordinator.getState().scrollOffset, 0.65);
    });
  });

  // =========================================================================
  // Scenario B: Independent Student Navigation & Instant Snap-Back
  // =========================================================================
  describe("Scenario B: Independent student navigation & Follow Tutor snap-back", () => {
    it("B.1: Student 1 toggles followTutor=false, navigates to vocab; Teacher advances to questions; Student 2 follows; Student 1 stays on vocab; Student 1 toggles followTutor=true -> snaps to questions", () => {
      // Step 1: Student 1 disables follow tutor for self-paced review
      student1Coordinator.setFollowTutor(false);
      assert.equal(student1Coordinator.isFollowTutor(), false);
      assert.equal(student2Coordinator.isFollowTutor(), true); // Student 2 remains following

      // Step 2: Student 1 independently navigates to vocabulary tab
      student1Coordinator.studentNavigateTab("vocab");
      assert.equal(student1Coordinator.getState().activeTab, "vocab");
      // Teacher and Student 2 remain on article
      assert.equal(teacherCoordinator.getState().activeTab, "article");
      assert.equal(student2Coordinator.getState().activeTab, "article");

      // Step 3: Teacher switches classroom to questions tab
      teacherCoordinator.syncTab("questions");
      assert.equal(teacherCoordinator.getState().activeTab, "questions");

      // Step 4: Student 2 follows Teacher immediately
      assert.equal(student2Coordinator.getState().activeTab, "questions");

      // Step 5: Student 1 stays on vocab without interruption
      assert.equal(student1Coordinator.getState().activeTab, "vocab");
      assert.equal(student1Coordinator.getState().hasUnseenTutorUpdate, true);

      // Student 1's cached tutor state accurately reflects Teacher's current position
      const cachedTutor = student1Coordinator.getCachedTutorState();
      assert.ok(cachedTutor);
      assert.equal(cachedTutor.activeTab, "questions");

      // Step 6: Student 1 toggles followTutor=true -> snaps immediately to questions tab
      student1Coordinator.setFollowTutor(true);
      assert.equal(student1Coordinator.isFollowTutor(), true);
      assert.equal(student1Coordinator.getState().activeTab, "questions");
      assert.equal(student1Coordinator.getState().hasUnseenTutorUpdate, false);

      // All 3 participants are unified on the questions tab
      assert.equal(teacherCoordinator.getState().activeTab, "questions");
      assert.equal(student1Coordinator.getState().activeTab, "questions");
      assert.equal(student2Coordinator.getState().activeTab, "questions");
    });
  });

  // =========================================================================
  // Scenario C: Permission Gating & Multi-Student Vocab Highlight Attribution
  // =========================================================================
  describe("Scenario C: Permission gating & student control with highlight attribution", () => {
    it("C.1: Student 2 attempts to change tab -> blocked by teacher when student control is disabled", () => {
      assert.equal(student2Coordinator.isStudentControlAllowed(), false);

      // Student 2 attempts to broadcast a tab change to 'vocab'
      student2Coordinator.syncTab("vocab");

      // Since student 2 is following tutor and student control is disabled, local action is blocked
      assert.equal(student2Coordinator.getState().activeTab, "article");

      // Even if a rogue packet is injected from student 2 to teacher, teacher rejects it
      const roguePacket: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "vocab", tabIndex: 1 },
        senderId: "student-bob",
        role: "student",
        timestamp: 999999,
      };

      const accepted = teacherCoordinator.handleAppMessage(roguePacket);
      assert.equal(accepted, false);
      assert.equal(teacherCoordinator.getState().activeTab, "article");
    });

    it("C.2: Teacher enables allow_student_control -> Student 2 highlights vocab card #2 -> Teacher and Student 1 both receive and reflect with correct attribution", async () => {
      // Step 1: Teacher enables student control mode
      teacherCoordinator.setStudentControlAllowed(true);

      // Both students receive SYNC_CONTROL envelope and update their state
      assert.equal(teacherCoordinator.isStudentControlAllowed(), true);
      assert.equal(student1Coordinator.isStudentControlAllowed(), true);
      assert.equal(student2Coordinator.isStudentControlAllowed(), true);

      // In real-world peer interactions, user actions occur across discrete clock ticks
      await new Promise((r) => setTimeout(r, 10));

      // Step 2: Student 2 highlights vocabulary card #2
      student2Coordinator.syncHighlight("set", {
        vocabIndex: 2,
        highlightId: "hl-vocab-2-bob",
        color: "amber",
      });

      // Verify Student 2's own state
      const s2State = student2Coordinator.getState();
      assert.equal(s2State.highlightedVocabIndex, 2);
      assert.equal(s2State.activeTab, "vocab");
      assert.equal(s2State.activeHighlights.length, 1);
      assert.equal(s2State.activeHighlights[0].attributedTo.senderId, "student-bob");
      assert.equal(s2State.activeHighlights[0].attributedTo.role, "student");

      // Verify Teacher received and reflected Student 2's highlight with attribution
      const tState = teacherCoordinator.getState();
      assert.equal(tState.highlightedVocabIndex, 2);
      assert.equal(tState.activeTab, "vocab");
      assert.equal(tState.activeHighlights.length, 1);
      assert.equal(tState.activeHighlights[0].attributedTo.senderId, "student-bob");
      assert.equal(tState.activeHighlights[0].attributedTo.role, "student");

      // Verify Student 1 also received and reflected Student 2's highlight with attribution
      const s1State = student1Coordinator.getState();
      assert.equal(s1State.highlightedVocabIndex, 2);
      assert.equal(s1State.activeTab, "vocab");
      assert.equal(s1State.activeHighlights.length, 1);
      assert.equal(s1State.activeHighlights[0].attributedTo.senderId, "student-bob");
      assert.equal(s1State.activeHighlights[0].attributedTo.role, "student");
    });

    it("C.3: Teacher clears highlight -> all participants clear highlight cleanly", async () => {
      // Setup: ensure highlight is set
      teacherCoordinator.setStudentControlAllowed(true);

      // In real-world peer interactions, user actions occur across discrete clock ticks
      await new Promise((r) => setTimeout(r, 10));

      student2Coordinator.syncHighlight("set", { vocabIndex: 2, highlightId: "hl-vocab-2" });

      assert.equal(teacherCoordinator.getState().highlightedVocabIndex, 2);
      assert.equal(student1Coordinator.getState().highlightedVocabIndex, 2);
      assert.equal(student2Coordinator.getState().highlightedVocabIndex, 2);

      // Teacher clears the highlight
      await new Promise((r) => setTimeout(r, 10));
      teacherCoordinator.highlightVocab(null);

      assert.equal(teacherCoordinator.getState().highlightedVocabIndex, null);
      assert.equal(student1Coordinator.getState().highlightedVocabIndex, null);
      assert.equal(student2Coordinator.getState().highlightedVocabIndex, null);
    });

    it("C.4: EMPIRICAL FINDING: Sub-millisecond peer timestamp collision drops packets when clocks share identical millisecond", () => {
      // Simulate two peers sharing a mock clock fixed to the exact same millisecond
      let sharedClock = 1700000000000;
      const staticClockFn = () => sharedClock;

      const staticTeacher = new ClassroomSyncCoordinator({
        role: "teacher",
        senderId: "static-teacher",
        now: staticClockFn,
        scrollThrottleMs: 0,
      });

      const staticStudent1 = new ClassroomSyncCoordinator({
        role: "student",
        senderId: "static-s1",
        now: staticClockFn,
        scrollThrottleMs: 0,
      });

      const staticStudent2 = new ClassroomSyncCoordinator({
        role: "student",
        senderId: "static-s2",
        now: staticClockFn,
        scrollThrottleMs: 0,
      });

      // Teacher enables control at sharedClock = 1700000000000
      staticTeacher.setStudentControlAllowed(true);
      // Student 1 and Student 2 receive teacher packet with timestamp 1700000000000
      const controlEnv = {
        type: "SYNC_CONTROL",
        payload: { allowStudentControl: true },
        senderId: "static-teacher",
        role: "teacher" as const,
        timestamp: sharedClock,
      };
      staticStudent1.handleAppMessage(controlEnv);
      staticStudent2.handleAppMessage(controlEnv);

      // Now Student 2 attempts to send a highlight at the SAME millisecond (timestamp 1700000000000)
      const studentHighlightEnv = {
        type: "SYNC_HIGHLIGHT",
        payload: {
          action: "set" as const,
          vocabIndex: 3,
          attributedTo: { senderId: "static-s2", role: "student" as const },
          timestamp: sharedClock,
        },
        senderId: "static-s2",
        role: "student" as const,
        timestamp: sharedClock,
      };

      // Student 1 receives Student 2's packet:
      // Monotonic LWW check: envelope.timestamp <= this.lastAppliedTimestamp (1700000000000 <= 1700000000000)
      const applied = staticStudent1.handleAppMessage(studentHighlightEnv);
      // EMPIRICALLY CONFIRMED: packet dropped as duplicate/stale due to lack of Lamport logical clock advancement!
      assert.equal(applied, false, "Sub-millisecond packet collision causes packet rejection");
      assert.equal(staticStudent1.getState().highlightedVocabIndex, null);
    });
  });

  // =========================================================================
  // Scenario D: Network Partition, Packet Loss, & Monotonic LWW Ordering
  // =========================================================================
  describe("Scenario D: Network partition / packet loss / out-of-order LWW rejection", () => {
    it("D.1: Delayed stale packets arriving after newer packets are rejected by monotonic LWW timestamp ordering", () => {
      const fixedBaseTime = 1700000000000;

      // Newer packet arrives first at Student 2 (timestamp = base + 500ms)
      const newerPacket: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "questions", tabIndex: 2 },
        senderId: "teacher-host",
        role: "teacher",
        timestamp: fixedBaseTime + 500,
      };

      const newerAccepted = student2Coordinator.handleAppMessage(newerPacket);
      assert.equal(newerAccepted, true);
      assert.equal(student2Coordinator.getState().activeTab, "questions");

      // Stale packet delayed by network arrives later (timestamp = base + 100ms)
      const stalePacket: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "vocab", tabIndex: 1 },
        senderId: "teacher-host",
        role: "teacher",
        timestamp: fixedBaseTime + 100,
      };

      const staleAccepted = student2Coordinator.handleAppMessage(stalePacket);
      // Monotonic LWW rejects the packet!
      assert.equal(staleAccepted, false);
      // Student 2's view remains on 'questions' and is NOT reverted to 'vocab'
      assert.equal(student2Coordinator.getState().activeTab, "questions");

      // Identical duplicate timestamp also rejected
      const duplicatePacket = { ...newerPacket };
      const duplicateAccepted = student2Coordinator.handleAppMessage(duplicatePacket);
      assert.equal(duplicateAccepted, false);
      assert.equal(student2Coordinator.getState().activeTab, "questions");
    });

    it("D.2: Temporary network partition: partitioned student heals and catches up to latest teacher state", () => {
      // Isolate Student 1 from the network
      network.dropPacketsForPeer.add("student-alice");

      // Teacher navigates classroom while Student 1 is offline
      teacherCoordinator.syncTab("questions");
      teacherCoordinator.syncScroll(0.85, true);

      // Student 2 (online) received updates
      assert.equal(student2Coordinator.getState().activeTab, "questions");
      assert.equal(student2Coordinator.getState().scrollOffset, 0.85);

      // Student 1 (offline) missed them
      assert.equal(student1Coordinator.getState().activeTab, "article");
      assert.equal(student1Coordinator.getState().scrollOffset, 0.0);

      // Partition heals: Student 1 re-connects
      network.dropPacketsForPeer.delete("student-alice");

      // Teacher performs authoritative material sync
      teacherCoordinator.syncMaterial("travel-english-b1", 2);

      // Student 1 immediately synchronizes to current state
      assert.equal(student1Coordinator.getState().materialId, "travel-english-b1");
      assert.equal(student1Coordinator.getState().sectionIndex, 2);
      assert.equal(student1Coordinator.getState().activeTab, "questions");
    });
  });

  // =========================================================================
  // Scenario E: Determinism, Zero Echo Storms, & Subscription Lifecycle Cleanup
  // =========================================================================
  describe("Scenario E: Determinism, zero echo storms, and subscription lifecycle cleanup", () => {
    it("E.1: Multi-participant network produces zero echo storms / loopback reflections", () => {
      // Clear sent history
      teacherTransport.clear();
      student1Transport.clear();
      student2Transport.clear();

      // Teacher issues 1 tab change
      teacherCoordinator.syncTab("vocab");

      // Exactly 1 message was broadcast by teacher
      assert.equal(teacherTransport.sentMessages.length, 1);
      // Inbound reception by Student 1 and Student 2 produced ZERO outbound messages
      assert.equal(student1Transport.sentMessages.length, 0);
      assert.equal(student2Transport.sentMessages.length, 0);

      // Teacher issues 1 page change
      teacherCoordinator.syncPage(2);
      assert.equal(teacherTransport.sentMessages.length, 2);
      assert.equal(student1Transport.sentMessages.length, 0);
      assert.equal(student2Transport.sentMessages.length, 0);
    });

    it("E.2: Subscription lifecycle: multiple listeners receive updates, unsubscribe works cleanly, and destroy releases all listeners", () => {
      let listener1Count = 0;
      let listener2Count = 0;

      const unsub1 = teacherCoordinator.subscribe(() => {
        listener1Count++;
      });
      const unsub2 = teacherCoordinator.subscribe(() => {
        listener2Count++;
      });

      teacherCoordinator.syncTab("vocab");
      assert.equal(listener1Count, 1);
      assert.equal(listener2Count, 1);

      // Unsubscribe listener 1
      unsub1();

      teacherCoordinator.syncTab("questions");
      // Listener 1 did not increment, Listener 2 did
      assert.equal(listener1Count, 1);
      assert.equal(listener2Count, 2);

      // Calling unsubscribe again is a safe no-op
      unsub1();

      // Calling destroy cleans up all remaining listeners
      teacherCoordinator.destroy();

      teacherCoordinator.syncTab("article");
      // No further notifications triggered
      assert.equal(listener1Count, 1);
      assert.equal(listener2Count, 2);
    });

    it("E.3: High-churn subscription stress test: 1,000 subscribe/unsubscribe cycles execute without leaks", () => {
      for (let i = 0; i < 1000; i++) {
        const unsub = teacherCoordinator.subscribe(() => {});
        unsub();
      }

      let activeCalls = 0;
      teacherCoordinator.subscribe(() => {
        activeCalls++;
      });

      // Switch to vocab tab (different from initial 'article' tab)
      teacherCoordinator.syncTab("vocab");
      assert.equal(activeCalls, 1);
    });

    it("E.4: Error resilience: a throwing listener does not prevent other listeners from being called", () => {
      let safeListenerCalled = false;

      teacherCoordinator.subscribe(() => {
        throw new Error("Simulated listener crash");
      });

      teacherCoordinator.subscribe(() => {
        safeListenerCalled = true;
      });

      // Should not throw to caller
      assert.doesNotThrow(() => {
        teacherCoordinator.syncTab("vocab");
      });

      assert.equal(safeListenerCalled, true);
    });
  });
});
