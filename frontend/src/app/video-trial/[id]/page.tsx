"use client";

import { useCallback } from "react";
import { useParams } from "next/navigation";
import { DailyClassroom } from "@/components/classroom/DailyClassroom";
import { VideoSessionToken } from "@/lib/classroomSession";
import { ApiError, request } from "@/lib/http";

export default function VideoTrialPage() {
  const { id } = useParams<{ id: string }>();
  const fetchTrialToken = useCallback(async () => {
    const data = await request<VideoSessionToken>(`/bookings/video-trials/${encodeURIComponent(id)}/token/`);
    if (!data?.token || !data?.room_url || !data?.session_name) {
      throw new ApiError(502, "The server returned an invalid video trial token", null);
    }
    return data;
  }, [id]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="mb-3 font-serif text-3xl font-bold text-ink">Video trial</h1>
      <p className="mb-8 text-ink-muted">
        Sign in with the invited tutor or student account, then enter the private classroom.
        This trial does not create a lesson booking or charge either participant.
      </p>
      <DailyClassroom
        bookingId={id}
        tokenFetcher={fetchTrialToken}
        joinLabel="Join video trial"
        partnerName="the other participant"
      />
    </main>
  );
}
