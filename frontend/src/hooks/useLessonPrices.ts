"use client";

import { api } from "@/lib/api";
import type { LessonPrice } from "@/lib/prices";
import { useApiData, type ApiDataState } from "./useApiData";

// One request is shared by every component on the page (a tutor grid renders many price labels). A failed load is
// not cached, so "Try again" and the next mount retry for real.
let shared: Promise<LessonPrice[]> | null = null;

function loadLessonPrices(): Promise<LessonPrice[]> {
  if (!shared) {
    shared = api.getLessonPrices().catch((err) => {
      shared = null;
      throw err;
    });
  }
  return shared;
}

/** The platform's per-lesson price in every currency, from GET /payments/lesson-prices/. Server truth only. */
export function useLessonPrices(): ApiDataState<LessonPrice[]> {
  return useApiData<LessonPrice[]>(loadLessonPrices, []);
}
