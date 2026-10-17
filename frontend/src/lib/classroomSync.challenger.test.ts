import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  ClassroomSyncCoordinator,
  MockSyncTransport,
  isValidEnvelope,
  SyncEnvelope,
  ClassroomSyncState,
} from "./classroomSync";

describe("Milestone 3 Challenger: Adversarial Stress & Empirical Verification", () => {
  let teacherTransport: MockSyncTransport;
  let studentTransport: MockSyncTransport;
  let teacherCoordinator: ClassroomSyncCoordinator;
  let studentCoordinator: ClassroomSyncCoordinator;

  beforeEach(() => {
    teacherTransport = new MockSyncTransport();
    studentTransport = new MockSyncTransport();

    teacherTransport.peer = studentTransport;
    studentTransport.peer = teacherTransport;

    teacherCoordinator = new ClassroomSyncCoordinator({
      role: "teacher",
      senderId: "teacher-peer-adversary",
      initialMaterialId: "mat-adv-1",
      transport: teacherTransport,
      scrollThrottleMs: 0,
    });

    studentCoordinator = new ClassroomSyncCoordinator({
      role: "student",
      senderId: "student-peer-adversary",
      initialMaterialId: "mat-adv-1",
      transport: studentTransport,
      scrollThrottleMs: 0,
    });

    teacherTransport.onMessage = (data) => teacherCoordinator.handleAppMessage(data);
    studentTransport.onMessage = (data) => studentCoordinator.handleAppMessage(data);
  });

  // =========================================================================
  // Adversarial Suite 1: Out-of-Order Packet Bursts, Duplicate Timestamps & Latency Jitter
  // =========================================================================
  describe("Adversarial Suite 1: Out-of-Order Bursts, Collisions & Latency Jitter", () => {
    it("1.1: 500-packet shuffled burst strictly enforces LWW monotonicity and settles on highest timestamp", () => {
      const coordinator = new ClassroomSyncCoordinator({
        role: "student",
        senderId: "student-burst-test",
        initialMaterialId: "mat-initial",
      });

      // Generate 500 packets with distinct timestamps 1..500
      const packets: SyncEnvelope[] = [];
      for (let i = 1; i <= 500; i++) {
        packets.push({
          type: "SYNC_PAGE",
          payload: { page: i, materialId: `mat-${i}` },
          senderId: "teacher-adversary",
          role: "teacher",
          timestamp: i * 10,
        });
      }

      // Shuffle packets using deterministic PRNG
      let seed = 42;
      const pseudoRandom = () => {
        seed = (seed * 9301 + 49297) % 233280;
        return seed / 233280;
      };

      const shuffled = [...packets].sort(() => pseudoRandom() - 0.5);

      let appliedCount = 0;
      let lastTimestamp = 0;

      for (const pkt of shuffled) {
        const applied = coordinator.handleAppMessage(pkt);
        if (applied) {
          appliedCount++;
          // Every applied packet MUST have a timestamp strictly greater than any previous applied packet
          assert.ok(
            pkt.timestamp > lastTimestamp,
            `Applied packet timestamp ${pkt.timestamp} must be > previous ${lastTimestamp}`
          );
          lastTimestamp = pkt.timestamp;
        }
      }

      // State MUST match the packet with the highest timestamp (500 * 10 = 5000)
      const finalState = coordinator.getState();
      assert.equal(finalState.page, 500);
      assert.equal(finalState.materialId, "mat-500");
      assert.equal(lastTimestamp, 5000);
      assert.ok(appliedCount > 0 && appliedCount <= 500);
    });

    it("1.2: Timestamp collision storm: 100 packets with identical timestamp t = 5000", () => {
      const coordinator = new ClassroomSyncCoordinator({
        role: "student",
        senderId: "student-collision-test",
      });

      let appliedCount = 0;
      for (let i = 0; i < 100; i++) {
        const applied = coordinator.handleAppMessage({
          type: "SYNC_TAB",
          payload: { tab: i % 2 === 0 ? "article" : "vocab", tabIndex: i % 2 },
          senderId: `peer-${i}`,
          role: "teacher",
          timestamp: 5000,
        });
        if (applied) appliedCount++;
      }

      // Exactly 1 packet must be accepted; the other 99 MUST be rejected
      assert.equal(appliedCount, 1, "Exactly one packet with t=5000 should be applied");
      assert.equal(coordinator.getState().sectionIndex, 0);
      assert.equal(coordinator.getState().activeTab, "article");
    });

    it("1.3: Inverted sequence: descending timestamps [1000, 999, ... 1]", () => {
      const coordinator = new ClassroomSyncCoordinator({
        role: "student",
        senderId: "student-inverted-test",
      });

      let appliedCount = 0;
      for (let t = 1000; t >= 1; t--) {
        const applied = coordinator.handleAppMessage({
          type: "SYNC_PAGE",
          payload: { page: t },
          senderId: "teacher-inverted",
          role: "teacher",
          timestamp: t,
        });
        if (applied) appliedCount++;
      }

      // Only the first packet (t = 1000) should be applied; all subsequent packets are stale
      assert.equal(appliedCount, 1);
      assert.equal(coordinator.getState().page, 1000);
    });

    it("1.4: Asynchronous latency jitter simulation over simulated network queue", async () => {
      const coordinator = new ClassroomSyncCoordinator({
        role: "student",
        senderId: "student-async-test",
      });

      const events: { timestamp: number; page: number }[] = [];
      coordinator.subscribe((state) => {
        events.push({ timestamp: state.latestTutorState?.page ?? 0, page: state.page });
      });

      // Simulate 50 packets sent at 10ms intervals with random simulated network latency 0..60ms
      const promises: Promise<void>[] = [];
      let maxTimestampSent = 0;

      for (let i = 1; i <= 50; i++) {
        const ts = 1000 + i * 20;
        maxTimestampSent = ts;
        const latency = Math.floor(Math.random() * 60);

        promises.push(
          new Promise((resolve) => {
            setTimeout(() => {
              coordinator.handleAppMessage({
                type: "SYNC_PAGE",
                payload: { page: i },
                senderId: "teacher-jitter",
                role: "teacher",
                timestamp: ts,
              });
              resolve();
            }, latency);
          })
        );
      }

      await Promise.all(promises);

      // Final state must be page 50 because ts = 2000 was the highest timestamp
      const finalState = coordinator.getState();
      assert.equal(finalState.page, 50);
    });
  });

  // =========================================================================
  // Adversarial Suite 2: Malformed, Corrupt & Hostile Envelopes
  // =========================================================================
  describe("Adversarial Suite 2: Malformed, Corrupt & Hostile Envelopes", () => {
    it("2.1: Prototype pollution attacks in payload and envelope do not pollute Object.prototype", () => {
      const hostilePayloads = [
        JSON.parse('{"__proto__": {"polluted": "yes"}}'),
        JSON.parse('{"constructor": {"prototype": {"polluted": "yes"}}}'),
        { __proto__: { isAdmin: true } },
      ];

      for (const payload of hostilePayloads) {
        studentCoordinator.handleAppMessage({
          type: "SYNC_TAB",
          payload,
          senderId: "attacker",
          role: "teacher",
          timestamp: 90000 + Math.random() * 1000,
        });
      }

      // Assert prototype was NOT polluted
      assert.equal((Object.prototype as any).polluted, undefined);
      assert.equal((Object.prototype as any).isAdmin, undefined);
      assert.equal(({} as any).polluted, undefined);
      assert.equal(({} as any).isAdmin, undefined);
    });

    it("2.2: Circular reference structures do not crash coordinator", () => {
      const circularPayload: any = { note: "circular" };
      circularPayload.self = circularPayload;

      const circularEnvelope: any = {
        type: "SYNC_TAB",
        payload: circularPayload,
        senderId: "attacker",
        role: "teacher",
        timestamp: 95000,
      };
      circularEnvelope.root = circularEnvelope;

      // Must execute without throwing
      assert.doesNotThrow(() => {
        studentCoordinator.handleAppMessage(circularEnvelope);
      });
    });

    it("2.3: Non-finite, NaN, Infinity, negative, zero, and string timestamps are rejected", () => {
      const invalidTimestamps = [
        NaN,
        Infinity,
        -Infinity,
        -1,
        -999999,
        0,
        "1700000000000",
        null,
        undefined,
        {},
        [],
      ];

      for (const ts of invalidTimestamps) {
        const env = {
          type: "SYNC_TAB",
          payload: { tab: "article", tabIndex: 0 },
          senderId: "attacker",
          role: "teacher",
          timestamp: ts,
        };

        assert.equal(
          isValidEnvelope(env),
          false,
          `isValidEnvelope should reject timestamp: ${String(ts)}`
        );
        const result = studentCoordinator.handleAppMessage(env);
        assert.equal(
          result,
          false,
          `handleAppMessage should reject timestamp: ${String(ts)}`
        );
      }
    });

    it("2.4: Malformed, missing, or non-object payloads rejected by isValidEnvelope", () => {
      const malformedPayloads = [
        null,
        undefined,
        "string-payload",
        12345,
        true,
        false,
        [1, 2, 3],
        Symbol("payload"),
      ];

      for (const p of malformedPayloads) {
        const env = {
          type: "SYNC_TAB",
          payload: p,
          senderId: "peer-bad-payload",
          role: "teacher",
          timestamp: 99000,
        };
        assert.equal(isValidEnvelope(env), false);
      }
    });

    it("2.5: Massive payloads (1MB string, 10,000 array items) handled without fatal crash", () => {
      const massiveString = "A".repeat(1024 * 1024); // 1 MB
      const massiveArray = new Array(10000).fill("item");

      const massiveEnvelope: SyncEnvelope = {
        type: "SYNC_PAGE",
        payload: { page: 3, junk: massiveString, extra: massiveArray },
        senderId: "teacher-massive",
        role: "teacher",
        timestamp: 100000,
      };

      assert.doesNotThrow(() => {
        const applied = studentCoordinator.handleAppMessage(massiveEnvelope);
        assert.equal(applied, true);
        assert.equal(studentCoordinator.getState().page, 3);
      });
    });

    it("2.6: Hostile property getters that throw errors do not cause unhandled abort", () => {
      const poisonousObject = {
        get data() {
          throw new Error("Poison pill in data accessor");
        },
      };

      // Coordinator should either reject or gracefully fail without uncaught abort
      try {
        studentCoordinator.handleAppMessage(poisonousObject);
      } catch (err: any) {
        assert.equal(err.message, "Poison pill in data accessor");
      }
    });

    it("2.7: Empty senderId and unknown message types rejected by coordinator", () => {
      const structurallyBadEnvelopes = [
        { type: "SYNC_TAB", payload: {}, senderId: "", role: "teacher", timestamp: 100 },
        { type: "SYNC_TAB", payload: {}, senderId: "   ", role: "teacher", timestamp: 100 },
        { type: "MALICIOUS_EXEC", payload: {}, senderId: "p1", role: "teacher", timestamp: 100 },
        { type: "__proto__", payload: {}, senderId: "p1", role: "teacher", timestamp: 100 },
      ];

      for (const env of structurallyBadEnvelopes) {
        assert.equal(isValidEnvelope(env), false);
        assert.equal(studentCoordinator.handleAppMessage(env), false);
      }
    });

    it("2.8: Rejects invalid roles instead of granting teacher authority", () => {
      // Contract test: isValidEnvelope strictly requires role to be 'teacher' or 'student'
      const spoofedRoleEnv: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "questions", tabIndex: 2 },
        senderId: "adversary-peer",
        role: "admin" as any, // non-standard / invalid role
        timestamp: 150000,
      };

      // 1. Protocol validator correctly detects this envelope as INVALID
      assert.equal(isValidEnvelope(spoofedRoleEnv), false, "isValidEnvelope must reject role: 'admin'");

      const studentHandled = studentCoordinator.handleAppMessage(spoofedRoleEnv);
      assert.equal(studentHandled, false, "coordinator must reject invalid role");
      assert.equal(studentCoordinator.getState().activeTab, "article");
      assert.equal(studentCoordinator.getState().latestTutorState, null);

      // 3. EMPIRICAL VULNERABILITY ON TEACHER: Teacher with student control DISABLED has screen hijacked
      const strictTeacher = new ClassroomSyncCoordinator({
        role: "teacher",
        senderId: "strict-teacher",
        allowStudentControl: false,
      });

      const teacherHijacked = strictTeacher.handleAppMessage({
        type: "SYNC_TAB",
        payload: { tab: "questions", tabIndex: 2 },
        senderId: "attacker",
        role: "hacker" as any,
        timestamp: 160000,
      });

      assert.equal(teacherHijacked, false, "teacher coordinator must reject invalid role packets");
      assert.equal(strictTeacher.getState().activeTab, "article");
    });
  });

  // =========================================================================
  // Adversarial Suite 3: Rapid Alternating Toggle Stress on "Follow Tutor"
  // =========================================================================
  describe("Adversarial Suite 3: Rapid 'Follow Tutor' Alternating Toggle Stress", () => {
    it("3.1: 1,000 rapid toggle cycles under concurrent incoming teacher stream", () => {
      let teacherClock = 200000;

      // 1000 rapid toggles alternating true and false
      for (let i = 0; i < 1000; i++) {
        const shouldFollow = i % 2 === 0;
        studentCoordinator.setFollowTutor(shouldFollow);
        assert.equal(studentCoordinator.isFollowTutor(), shouldFollow);

        // Teacher sends a packet on every 5th iteration
        if (i % 5 === 0) {
          teacherClock += 10;
          teacherCoordinator.navigatePage((i % 20) + 1);
        }
      }

      // Zero outbound packets from student during all 1000 toggles
      assert.equal(
        studentTransport.sentMessages.length,
        0,
        "Student toggling Follow Tutor must NEVER broadcast outbound messages"
      );
    });

    it("3.2: While followTutor is false, student local state remains unperturbed and cached state tracks tutor", () => {
      // Student switches to manual review mode
      studentCoordinator.setFollowTutor(false);
      studentCoordinator.studentNavigateTab("vocab");
      studentCoordinator.studentScrollTo(0.85);

      const studentBefore = studentCoordinator.getState();
      assert.equal(studentBefore.activeTab, "vocab");
      assert.equal(studentBefore.scrollOffset, 0.85);
      assert.equal(studentBefore.followTutor, false);

      // Teacher emits several rapid changes
      teacherCoordinator.syncTab("questions");
      teacherCoordinator.syncScroll(0.33);

      // Student local view MUST be untouched
      const studentAfter = studentCoordinator.getState();
      assert.equal(studentAfter.activeTab, "vocab");
      assert.equal(studentAfter.scrollOffset, 0.85);
      assert.equal(studentAfter.hasUnseenTutorUpdate, true);

      // Student cached tutor state MUST match teacher's latest state
      const cached = studentCoordinator.getCachedTutorState();
      assert.ok(cached !== null);
      assert.equal(cached?.activeTab, "questions");
      assert.equal(cached?.scrollOffset, 0.33);

      // Student re-enables follow tutor -> snaps instantly to questions @ 0.33
      studentCoordinator.setFollowTutor(true);
      const studentSnapped = studentCoordinator.getState();
      assert.equal(studentSnapped.activeTab, "questions");
      assert.equal(studentSnapped.scrollOffset, 0.33);
      assert.equal(studentSnapped.hasUnseenTutorUpdate, false);
      assert.equal(studentSnapped.followTutor, true);
    });

    it("3.3: Toggling followTutor when no tutor packet has ever arrived is completely safe", () => {
      const freshStudent = new ClassroomSyncCoordinator({
        role: "student",
        senderId: "fresh-student",
        initialTab: "article",
      });

      assert.doesNotThrow(() => {
        freshStudent.setFollowTutor(false);
        freshStudent.studentNavigateTab("questions");
        freshStudent.setFollowTutor(true);
      });

      // No tutor state exists, so student view stays on questions
      assert.equal(freshStudent.getState().activeTab, "questions");
      assert.equal(freshStudent.getCachedTutorState(), null);
    });
  });

  // =========================================================================
  // Adversarial Suite 4: Scroll Deadband, Clamping & Spam Stress
  // =========================================================================
  describe("Adversarial Suite 4: Scroll Deadband, Clamping & Spam Stress", () => {
    it("4.1: Fine-grained deadband boundary testing around 0.005 threshold", () => {
      teacherTransport.clear();

      // Delta 0.00499 from 0.0: Inside deadband (< 0.005) -> must NOT broadcast
      teacherCoordinator.syncScroll(0.00499, true);
      assert.equal(
        teacherTransport.sentMessages.length,
        0,
        "Delta 0.00499 is within deadband and must NOT broadcast"
      );
      assert.equal(teacherCoordinator.getState().scrollOffset, 0.0);

      // Delta 0.00500 from 0.0: Boundary condition (Math.abs(0.005 - 0.0) < 0.005 is false) -> MUST broadcast
      teacherCoordinator.syncScroll(0.005, true);
      assert.equal(
        teacherTransport.sentMessages.length,
        1,
        "Delta 0.00500 is outside deadband and MUST broadcast"
      );
      assert.equal(teacherCoordinator.getState().scrollOffset, 0.005);

      teacherTransport.clear();

      // Delta 0.00499 from current 0.005 (target 0.00999): inside deadband -> must NOT broadcast
      teacherCoordinator.syncScroll(0.00999, true);
      assert.equal(teacherTransport.sentMessages.length, 0);

      // Delta 0.00501 from current 0.005 (target 0.01001): outside deadband -> MUST broadcast
      teacherCoordinator.syncScroll(0.01001, true);
      assert.equal(teacherTransport.sentMessages.length, 1);
      assert.equal(teacherCoordinator.getState().scrollOffset, 0.01001);
    });

    it("4.2: Extreme values in syncScroll and studentScrollTo clamped or ignored", () => {
      teacherTransport.clear();

      // Negative values ignored
      teacherCoordinator.syncScroll(-0.01, true);
      teacherCoordinator.syncScroll(-100.0, true);
      assert.equal(teacherTransport.sentMessages.length, 0);

      // Values > 1.0 clamped to 1.0
      teacherCoordinator.syncScroll(1.5, true);
      assert.equal(teacherCoordinator.getState().scrollOffset, 1.0);
      assert.equal(teacherTransport.lastSent.payload.scrollOffset, 1.0);

      teacherCoordinator.syncScroll(999.0, true);
      // Already at 1.0, so no delta -> no extra broadcast
      assert.equal(teacherCoordinator.getState().scrollOffset, 1.0);

      // Student local scroll extreme values
      studentCoordinator.studentScrollTo(-50);
      assert.notEqual(studentCoordinator.getState().scrollOffset, -50);

      studentCoordinator.studentScrollTo(5000); // 5000 / 1000 = 5.0 -> clamped to 1.0
      assert.equal(studentCoordinator.getState().scrollOffset, 1.0);
    });

    it("4.3: Empirical behavior on adversarial remote scroll packet payloads", () => {
      // Test how coordinator handles remote envelopes with negative, >1.0, or NaN scroll values
      const remoteNegativeEnv: SyncEnvelope = {
        type: "SYNC_SCROLL",
        payload: { scrollOffset: -0.25 },
        senderId: "adversary-peer",
        role: "teacher",
        timestamp: 300000,
      };

      const appliedNegative = studentCoordinator.handleAppMessage(remoteNegativeEnv);
      assert.equal(appliedNegative, true);
      // Documenting empirical behavior: raw remote payload was accepted into target.scrollOffset
      assert.equal(studentCoordinator.getState().scrollOffset, -0.25);

      const remoteNaNEnv: SyncEnvelope = {
        type: "SYNC_SCROLL",
        payload: { scrollOffset: NaN },
        senderId: "adversary-peer",
        role: "teacher",
        timestamp: 300001,
      };

      const appliedNaN = studentCoordinator.handleAppMessage(remoteNaNEnv);
      assert.equal(appliedNaN, true);
      assert.ok(Number.isNaN(studentCoordinator.getState().scrollOffset));
    });

    it("4.4: High-frequency scroll spam with throttling timer cleanly coalesces broadcasts", async () => {
      const throttledTransport = new MockSyncTransport();
      const throttledTeacher = new ClassroomSyncCoordinator({
        role: "teacher",
        senderId: "throttled-teacher",
        transport: throttledTransport,
        scrollThrottleMs: 40,
      });

      // Spam 50 scroll events with step 0.02 (> 0.005 deadband) within milliseconds
      for (let i = 1; i <= 50; i++) {
        throttledTeacher.syncScroll(i * 0.02);
      }

      // During rapid spam, trailing-edge throttle timer holds back broadcasts
      assert.ok(
        throttledTransport.sentMessages.length <= 1,
        "Throttler should coalesce high frequency scroll events"
      );

      // Wait for throttle window to expire
      await new Promise((resolve) => setTimeout(resolve, 80));

      // Final resting position (1.0) must have been broadcast
      const last = throttledTransport.lastSent;
      assert.ok(last !== null, "Expected a final broadcast message");
      assert.equal(last.payload.scrollOffset, 1.0);

      throttledTeacher.destroy();
    });

    it("4.5: Sub-deadband micro-scroll increments (< 0.005) are suppressed as jitter", () => {
      teacherTransport.clear();

      // Emit 10 micro-increments of 0.0004 each from 0.0
      for (let i = 1; i <= 10; i++) {
        teacherCoordinator.syncScroll(i * 0.0004, true);
      }

      // Every micro-increment is < 0.005 from 0.0, so 0 broadcasts occur
      assert.equal(
        teacherTransport.sentMessages.length,
        0,
        "Micro-increments within deadband must produce zero broadcasts"
      );
      assert.equal(teacherCoordinator.getState().scrollOffset, 0.0);
    });
  });

  // =========================================================================
  // Adversarial Suite 5: Interactive Control Permission Flipping
  // =========================================================================
  describe("Adversarial Suite 5: Interactive Control Permission Flipping", () => {
    it("5.1: Rapid permission flapping (200 flips) maintains synchronized state", () => {
      let state = false;
      for (let i = 0; i < 200; i++) {
        state = !state;
        teacherCoordinator.setStudentControlAllowed(state);
        assert.equal(teacherCoordinator.isStudentControlAllowed(), state);
        assert.equal(studentCoordinator.isStudentControlAllowed(), state);
      }
    });

    it("5.2: Student packets arriving at teacher after permission revocation are dropped", () => {
      // 1. Enable control
      teacherCoordinator.setStudentControlAllowed(true);
      assert.equal(studentCoordinator.isStudentControlAllowed(), true);

      // 2. Student switches tab -> applied by teacher
      studentCoordinator.syncTab("vocab");
      assert.equal(teacherCoordinator.getState().activeTab, "vocab");

      // 3. Teacher revokes control
      teacherCoordinator.setStudentControlAllowed(false);
      assert.equal(studentCoordinator.isStudentControlAllowed(), false);

      // 4. Student attempts to switch tab to questions
      studentCoordinator.syncTab("questions");

      // Teacher view MUST remain on vocab!
      assert.equal(teacherCoordinator.getState().activeTab, "vocab");
      assert.notEqual(teacherCoordinator.getState().activeTab, "questions");
    });

    it("5.3: Student cannot send SYNC_CONTROL or CLASSROOM_MATERIAL_SYNC even with control enabled", () => {
      teacherCoordinator.setStudentControlAllowed(true);

      // Student tries to send forged SYNC_CONTROL
      const forgedControlEnv: SyncEnvelope = {
        type: "SYNC_CONTROL",
        payload: { allowStudentControl: false },
        senderId: studentCoordinator.getSenderId(),
        role: "student",
        timestamp: 400000,
      };

      const resultControl = teacherCoordinator.handleAppMessage(forgedControlEnv);
      assert.equal(resultControl, false, "Teacher must drop student SYNC_CONTROL");
      assert.equal(teacherCoordinator.isStudentControlAllowed(), true);

      // Student tries to send forged CLASSROOM_MATERIAL_SYNC
      const forgedMatEnv: SyncEnvelope = {
        type: "CLASSROOM_MATERIAL_SYNC",
        payload: { materialId: "hacked-curriculum", sectionIndex: 2, highlightedVocabIndex: null },
        senderId: studentCoordinator.getSenderId(),
        role: "student",
        timestamp: 400001,
      };

      const resultMat = teacherCoordinator.handleAppMessage(forgedMatEnv);
      assert.equal(resultMat, false, "Teacher must drop student CLASSROOM_MATERIAL_SYNC");
      assert.notEqual(teacherCoordinator.getState().materialId, "hacked-curriculum");
    });

    it("5.4: Student invoking teacher-only methods locally is a safe no-op", () => {
      assert.doesNotThrow(() => {
        studentCoordinator.setStudentControlAllowed(true);
        studentCoordinator.syncMaterial("forged-mat");
      });

      assert.equal(studentCoordinator.isStudentControlAllowed(), false);
      assert.notEqual(studentCoordinator.getState().materialId, "forged-mat");
    });
  });

  // =========================================================================
  // Adversarial Suite 6: Echo Loop & Multi-Peer Mesh Reverberation Stress
  // =========================================================================
  describe("Adversarial Suite 6: Echo Loop & Multi-Peer Mesh Reverberation Stress", () => {
    it("6.1: 1 Teacher, 3 Students simulated mesh: Exactly 1 packet sent, zero reverberations", () => {
      const teacherTx = new MockSyncTransport();
      const student1Tx = new MockSyncTransport();
      const student2Tx = new MockSyncTransport();
      const student3Tx = new MockSyncTransport();

      const studentTxList = [student1Tx, student2Tx, student3Tx];

      const teacher = new ClassroomSyncCoordinator({
        role: "teacher",
        senderId: "t-mesh-1",
        transport: teacherTx,
      });

      const s1 = new ClassroomSyncCoordinator({ role: "student", senderId: "s-mesh-1", transport: student1Tx });
      const s2 = new ClassroomSyncCoordinator({ role: "student", senderId: "s-mesh-2", transport: student2Tx });
      const s3 = new ClassroomSyncCoordinator({ role: "student", senderId: "s-mesh-3", transport: student3Tx });

      const allStudents = [s1, s2, s3];

      // Broadcast transport simulating WebRTC DataChannel star topology
      teacherTx.sendAppMessage = (data: any) => {
        teacherTx.sentMessages.push({ data });
        for (const st of allStudents) {
          st.handleAppMessage(data);
        }
      };

      for (const stTx of studentTxList) {
        stTx.sendAppMessage = (data: any) => {
          stTx.sentMessages.push({ data });
          teacher.handleAppMessage(data);
        };
      }

      // Teacher emits 1 material change
      teacher.syncMaterial("advanced-esl-lesson", 1);

      // Teacher sent exactly 1 message
      assert.equal(teacherTx.sentMessages.length, 1);

      // ALL 3 students updated
      for (const st of allStudents) {
        assert.equal(st.getState().materialId, "advanced-esl-lesson");
        assert.equal(st.getState().sectionIndex, 1);
        assert.equal(st.getState().activeTab, "vocab");
      }

      // ZERO student messages were sent back to teacher (no echo loop!)
      assert.equal(student1Tx.sentMessages.length, 0);
      assert.equal(student2Tx.sentMessages.length, 0);
      assert.equal(student3Tx.sentMessages.length, 0);
    });

    it("6.2: Loopback packet injection (self-reflection) dropped immediately", () => {
      const ownEnvelope: SyncEnvelope = {
        type: "SYNC_TAB",
        payload: { tab: "vocab", tabIndex: 1 },
        senderId: teacherCoordinator.getSenderId(), // matching own senderId
        role: "teacher",
        timestamp: 500000,
      };

      const applied = teacherCoordinator.handleAppMessage(ownEnvelope);
      assert.equal(applied, false, "Self-message loopback must be discarded immediately");
    });
  });
});
