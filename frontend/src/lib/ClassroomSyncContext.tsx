"use client";

import React, { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  ClassroomSyncCoordinator,
  ClassroomSyncOptions,
  ClassroomSyncState,
  CurriculumTabId,
  HighlightAction,
  SyncRole,
} from "./classroomSync";

export interface ClassroomSyncContextValue {
  coordinator: ClassroomSyncCoordinator;
  state: ClassroomSyncState;
  activeTab: CurriculumTabId;
  sectionIndex: number;
  highlightedVocabIndex: number | null;
  followTutor: boolean;
  allowStudentControl: boolean;
  hasUnseenTutorUpdate: boolean;

  // Action dispatches
  syncTab: (tab: CurriculumTabId | number) => void;
  syncHighlight: (action: HighlightAction, options?: { vocabIndex?: number | null; [key: string]: any }) => void;
  syncMaterial: (materialId: string | null, sectionIndex?: number) => void;
  setFollowTutor: (enabled: boolean) => void;
  setStudentControlAllowed: (allowed: boolean) => void;

  // Transport integration
  registerTransport: (sendFn: ((data: any, to?: string) => void) | null) => void;
  handleAppMessage: (eventOrData: any, fromId?: string) => boolean;
}

const ClassroomSyncContext = createContext<ClassroomSyncContextValue | null>(null);

export function useClassroomSyncContext(): ClassroomSyncContextValue | null {
  return useContext(ClassroomSyncContext);
}

export function useClassroomSync(options: ClassroomSyncOptions): ClassroomSyncContextValue {
  const coordinatorRef = useRef<ClassroomSyncCoordinator | null>(null);

  if (!coordinatorRef.current) {
    coordinatorRef.current = new ClassroomSyncCoordinator(options);
  }
  const coordinator = coordinatorRef.current;

  const [syncState, setSyncState] = useState<ClassroomSyncState>(() => coordinator.getState());

  useEffect(() => {
    const unsubscribe = coordinator.subscribe((newState) => {
      setSyncState(newState);
    });
    return () => {
      unsubscribe();
      coordinator.destroy();
    };
  }, [coordinator]);

  // Synchronize material changes when teacher switches material
  useEffect(() => {
    if (
      options.initialMaterialId &&
      options.role === "teacher" &&
      syncState.materialId !== options.initialMaterialId
    ) {
      coordinator.syncMaterial(options.initialMaterialId);
    }
  }, [options.initialMaterialId, options.role, coordinator, syncState.materialId]);

  const registerTransport = useCallback(
    (sendFn: ((data: any, to?: string) => void) | null) => {
      if (sendFn) {
        coordinator.setTransport({ sendAppMessage: sendFn });
      } else {
        coordinator.setTransport(null);
      }
    },
    [coordinator]
  );

  const handleAppMessage = useCallback(
    (eventOrData: any, fromId?: string) => {
      return coordinator.handleAppMessage(
        eventOrData && typeof eventOrData === "object" && "data" in eventOrData
          ? eventOrData
          : { data: eventOrData, fromId }
      );
    },
    [coordinator]
  );

  const syncTab = useCallback(
    (tab: CurriculumTabId | number) => coordinator.syncTab(tab),
    [coordinator]
  );

  const syncHighlight = useCallback(
    (action: HighlightAction, opts?: { vocabIndex?: number | null; [key: string]: any }) =>
      coordinator.syncHighlight(action, opts || {}),
    [coordinator]
  );

  const syncMaterial = useCallback(
    (materialId: string | null, sectionIndex?: number) =>
      coordinator.syncMaterial(materialId, sectionIndex),
    [coordinator]
  );

  const setFollowTutor = useCallback(
    (enabled: boolean) => coordinator.setFollowTutor(enabled),
    [coordinator]
  );

  const setStudentControlAllowed = useCallback(
    (allowed: boolean) => coordinator.setStudentControlAllowed(allowed),
    [coordinator]
  );

  return useMemo(
    () => ({
      coordinator,
      state: syncState,
      activeTab: syncState.activeTab,
      sectionIndex: syncState.sectionIndex,
      highlightedVocabIndex: syncState.highlightedVocabIndex,
      followTutor: syncState.followTutor,
      allowStudentControl: syncState.allowStudentControl,
      hasUnseenTutorUpdate: syncState.hasUnseenTutorUpdate,
      syncTab,
      syncHighlight,
      syncMaterial,
      setFollowTutor,
      setStudentControlAllowed,
      registerTransport,
      handleAppMessage,
    }),
    [
      coordinator,
      syncState,
      syncTab,
      syncHighlight,
      syncMaterial,
      setFollowTutor,
      setStudentControlAllowed,
      registerTransport,
      handleAppMessage,
    ]
  );
}

export function ClassroomSyncProvider({
  value,
  children,
}: {
  value: ClassroomSyncContextValue;
  children: React.ReactNode;
}) {
  return <ClassroomSyncContext.Provider value={value}>{children}</ClassroomSyncContext.Provider>;
}
