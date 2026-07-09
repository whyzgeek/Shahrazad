export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type Topic = {
  topic_id: string;
  title_en: string;
  title_ar: string;
  level_hint: string;
};

export type LiveSessionStart = {
  session_id: string;
  topic_id: string;
  room_name: string;
  token: string;
  livekit_url: string;
};

export type SessionError = {
  id: string;
  kind: string;
  learner_text: string;
  correct_form: string;
  explanation_ar: string;
  explanation_en: string;
  resolved_at: string | null;
};

export async function fetchTopics(): Promise<Topic[]> {
  const res = await fetch(`${API_URL}/topics`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load topics");
  return res.json();
}

export async function startLiveSession(topicId: string): Promise<LiveSessionStart> {
  const res = await fetch(`${API_URL}/sessions/live`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic_id: topicId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchSessionErrors(sessionId: string): Promise<SessionError[]> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/errors`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load errors");
  const data = await res.json();
  return data.errors ?? [];
}

export function ttsUrl(text: string): string {
  return `${API_URL}/tts?text=${encodeURIComponent(text)}`;
}

export async function acknowledgeError(errorId: string): Promise<void> {
  await fetch(`${API_URL}/errors/${errorId}/acknowledge`, { method: "POST" });
}
