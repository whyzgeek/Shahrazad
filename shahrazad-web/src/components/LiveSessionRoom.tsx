"use client";

import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
  useParticipants,
  useRoomContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { ConnectionState, ParticipantKind, RoomEvent } from "livekit-client";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  acknowledgeError,
  fetchSessionErrors,
  ttsUrl,
  type SessionError,
} from "@/lib/api";

type TranscriptSection = "conversation" | "practice";

type TranscriptLine = {
  id: string;
  role: "learner" | "tutor";
  text: string;
  section: TranscriptSection;
};

type FlowStage = "conversation" | "review" | "summary" | "complete";

type FlowProgress = {
  turns_done: number;
  turns_target: number;
  drills_done: number;
  drills_target: number;
  drills_passed: number;
};

type SessionSummary = {
  turns_done: number;
  errors_total: number;
  errors_resolved: number;
  drills_done: number;
  drills_passed: number;
};

const DEFAULT_PROGRESS: FlowProgress = {
  turns_done: 0,
  turns_target: 6,
  drills_done: 0,
  drills_target: 0,
  drills_passed: 0,
};

type LiveConfig = {
  sessionId: string;
  token: string;
  serverUrl: string;
  topicId: string;
};

function SessionInner({
  sessionId,
  locale,
}: {
  sessionId: string;
  locale: string;
}) {
  const t = useTranslations();
  const room = useRoomContext();
  const participants = useParticipants();
  const connection = useConnectionState();
  const { state: agentState, audioTrack } = useVoiceAssistant();
  const [errorCount, setErrorCount] = useState(0);
  const [errors, setErrors] = useState<SessionError[]>([]);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const transcriptSectionRef = useRef<TranscriptSection>("conversation");
  const [drillActive, setDrillActive] = useState(false);
  const [practiceSentenceCount, setPracticeSentenceCount] = useState(3);
  const [agentReady, setAgentReady] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [stage, setStage] = useState<FlowStage>("conversation");
  const [progress, setProgress] = useState<FlowProgress>(DEFAULT_PROGRESS);
  const [summary, setSummary] = useState<SessionSummary | null>(null);

  const agentJoined = useMemo(
    () =>
      agentReady ||
      participants.some((p) => p.kind === ParticipantKind.AGENT || p.identity.includes("agent")),
    [agentReady, participants],
  );

  const refreshErrors = useCallback(async () => {
    try {
      const list = await fetchSessionErrors(sessionId);
      setErrors(list);
      setErrorCount(list.filter((e) => !e.resolved_at).length);
    } catch {
      /* ignore polling errors */
    }
  }, [sessionId]);

  useEffect(() => {
    refreshErrors();
    const interval = setInterval(refreshErrors, 8000);
    return () => clearInterval(interval);
  }, [refreshErrors]);

  useEffect(() => {
    const el = transcriptRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lines]);

  useEffect(() => {
    const onData = (
      payload: Uint8Array,
      _participant: unknown,
      _kind: unknown,
      topic?: string,
    ) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload));

        if (topic === "shahrazad-session" && msg.type === "session_ready") {
          setAgentReady(true);
        }

        if (topic === "shahrazad-transcript") {
          if (msg.type === "section" && (msg.section === "practice" || msg.section === "conversation")) {
            transcriptSectionRef.current = msg.section;
          }
          if (msg.type === "transcript" && msg.text) {
            const role = msg.role === "tutor" ? "tutor" : "learner";
            const section: TranscriptSection =
              msg.section === "practice" || msg.section === "conversation"
                ? msg.section
                : transcriptSectionRef.current;
            setLines((prev) => [
              ...prev,
              {
                id: `${Date.now()}-${role}-${prev.length}`,
                role,
                text: String(msg.text),
                section,
              },
            ]);
          }
        }

        if (topic === "shahrazad-control") {
          if (msg.type === "commit_ack") {
            setCommitting(false);
            if (msg.transcript) {
              setLines((prev) => [
                ...prev,
                {
                  id: `${Date.now()}-learner-${prev.length}`,
                  role: "learner",
                  text: String(msg.transcript),
                  section: transcriptSectionRef.current,
                },
              ]);
            }
          }
          if (msg.type === "commit_error") {
            setCommitting(false);
          }
        }

        if (topic === "shahrazad-errors" && msg.type === "error_count") {
          setErrorCount(msg.total ?? 0);
          refreshErrors();
        }
        if (topic === "shahrazad-drill") {
          if (msg.type === "drill_started") {
            setDrillActive(true);
            transcriptSectionRef.current = "practice";
          }
          if (msg.type === "drill_completed") {
            setDrillActive(false);
            transcriptSectionRef.current = "conversation";
            refreshErrors();
          }
        }
        if (topic === "shahrazad-flow") {
          if (msg.type === "stage") {
            setStage(msg.stage as FlowStage);
            if (msg.progress) setProgress(msg.progress as FlowProgress);
          }
          if (msg.type === "session_summary") {
            setSummary(msg as SessionSummary);
            refreshErrors();
          }
        }
      } catch {
        /* ignore */
      }
    };

    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
    };
  }, [room, refreshErrors]);

  const commitTurn = useCallback(async () => {
    if (committing || !agentJoined) return;
    setCommitting(true);
    try {
      await room.localParticipant.publishData(
        new TextEncoder().encode(JSON.stringify({ type: "commit_turn" })),
        { topic: "shahrazad-control", reliable: true },
      );
    } catch {
      setCommitting(false);
    }
    window.setTimeout(() => setCommitting(false), 15000);
  }, [agentJoined, committing, room]);

  const startDrill = useCallback(
    (errorId: string) => {
      const payload = new TextEncoder().encode(
        JSON.stringify({
          type: "start_drill",
          error_entry_id: errorId,
          sentence_count: practiceSentenceCount,
        }),
      );
      room.localParticipant.publishData(payload, { topic: "shahrazad-drill", reliable: true });
    },
    [practiceSentenceCount, room],
  );

  const skipStage = useCallback(() => {
    const payload = new TextEncoder().encode(JSON.stringify({ type: "skip_stage" }));
    room.localParticipant.publishData(payload, { topic: "shahrazad-control", reliable: true });
  }, [room]);

  const statusLabel = useMemo(() => {
    if (connection !== ConnectionState.Connected) return t("session.connecting");
    if (!agentJoined) return t("session.waitingForAgent");
    if (committing) return t("session.committing");
    if (drillActive) return t("session.lessonPaused");
    if (agentState === "speaking") return t("session.agentSpeaking");
    return t("session.yourTurn");
  }, [agentJoined, agentState, committing, connection, drillActive, t]);

  const transcriptBlocks = useMemo(() => {
    const blocks: { section: TranscriptSection; lines: TranscriptLine[] }[] = [];
    for (const line of lines) {
      const last = blocks[blocks.length - 1];
      if (!last || last.section !== line.section) {
        blocks.push({ section: line.section, lines: [line] });
      } else {
        last.lines.push(line);
      }
    }
    return blocks;
  }, [lines]);

  const stageIndex = stage === "conversation" ? 0 : stage === "review" ? 1 : 2;
  const steps = [
    {
      label: t("flow.stageConversation"),
      detail: t("flow.turnsProgress", {
        done: Math.min(progress.turns_done, progress.turns_target),
        target: progress.turns_target,
      }),
    },
    {
      label: t("flow.stageReview"),
      detail:
        progress.drills_done > 0
          ? t("flow.drillsProgress", { done: progress.drills_done })
          : "",
    },
    { label: t("flow.stageSummary"), detail: "" },
  ];
  const sessionComplete = stage === "complete";

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="rounded-2xl border border-shahrazad-gold/30 bg-white/80 p-6 shadow-sm">
        <ol className="mb-5 flex items-center gap-2">
          {steps.map((step, i) => (
            <li key={step.label} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex w-full items-center gap-2">
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    i < stageIndex || sessionComplete
                      ? "bg-shahrazad-gold text-shahrazad-ink"
                      : i === stageIndex
                        ? "bg-shahrazad-dusk text-white"
                        : "bg-shahrazad-dusk/15 text-shahrazad-dusk/60"
                  }`}
                >
                  {i < stageIndex || sessionComplete ? "✓" : i + 1}
                </span>
                <span
                  className={`text-sm font-medium ${
                    i === stageIndex && !sessionComplete
                      ? "text-shahrazad-ink"
                      : "text-shahrazad-dusk/60"
                  }`}
                >
                  {step.label}
                </span>
              </div>
              {step.detail && (
                <span className="w-full ps-9 text-xs text-shahrazad-dusk/50">{step.detail}</span>
              )}
            </li>
          ))}
        </ol>

        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-shahrazad-dusk/70">
              {connection === ConnectionState.Connected
                ? agentJoined
                  ? t("session.connected")
                  : t("session.waitingForAgent")
                : t("session.connecting")}
            </p>
            <p className="font-medium">{statusLabel}</p>
          </div>
          <span className="rounded-full bg-shahrazad-gold/20 px-3 py-1 text-sm font-semibold text-shahrazad-dusk">
            {t("session.errors")}: {errorCount}
          </span>
        </div>

        {audioTrack && (
          <div className="mb-6 h-16">
            <BarVisualizer trackRef={audioTrack} barCount={24} />
          </div>
        )}

        {!agentJoined && connection === ConnectionState.Connected && (
          <p className="mb-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Start the agent worker:{" "}
            <code className="text-xs">shahrazad-agent dev</code>
          </p>
        )}

        {sessionComplete && summary ? (
          <div className="mb-6 rounded-xl border border-shahrazad-gold/40 bg-shahrazad-sand/60 p-5 text-center">
            <p className="mb-3 text-lg font-semibold text-shahrazad-ink">
              {t("flow.summaryTitle")}
            </p>
            <dl className="mb-4 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-shahrazad-dusk/60">{t("flow.summaryTurns")}</dt>
                <dd className="text-xl font-bold">{summary.turns_done}</dd>
              </div>
              <div>
                <dt className="text-shahrazad-dusk/60">{t("flow.summaryNotes")}</dt>
                <dd className="text-xl font-bold">{summary.errors_total}</dd>
              </div>
              <div>
                <dt className="text-shahrazad-dusk/60">{t("flow.summaryResolved")}</dt>
                <dd className="text-xl font-bold">{summary.errors_resolved}</dd>
              </div>
              <div>
                <dt className="text-shahrazad-dusk/60">{t("flow.summaryDrillsPassed")}</dt>
                <dd className="text-xl font-bold">{summary.drills_passed}</dd>
              </div>
            </dl>
            <Link
              href={`/${locale}`}
              className="inline-block rounded-xl bg-shahrazad-gold px-6 py-3 font-semibold text-shahrazad-ink shadow hover:brightness-105"
            >
              {t("flow.startNew")}
            </Link>
          </div>
        ) : (
          <div className="mb-6 space-y-2">
            {(stage === "review" || drillActive) && (
              <p className="rounded-lg bg-shahrazad-sand/60 px-4 py-2 text-sm text-shahrazad-dusk">
                {drillActive ? t("session.lessonPaused") : t("flow.reviewHint")}
              </p>
            )}
            {stage === "conversation" && !drillActive && (
              <button
                type="button"
                onClick={commitTurn}
                disabled={
                  connection !== ConnectionState.Connected ||
                  !agentJoined ||
                  committing
                }
                className="w-full rounded-xl bg-shahrazad-gold py-4 text-lg font-semibold text-shahrazad-ink shadow hover:brightness-105 disabled:opacity-40"
              >
                {committing ? t("session.committing") : t("session.doneSpeaking")}
              </button>
            )}
            {!drillActive && (
              <button
                type="button"
                onClick={skipStage}
                disabled={connection !== ConnectionState.Connected || !agentJoined}
                className="w-full rounded-xl border border-shahrazad-dusk/25 py-2 text-sm text-shahrazad-dusk hover:bg-white/60 disabled:opacity-40"
              >
                {t("flow.skipStage")}
              </button>
            )}
          </div>
        )}

        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-shahrazad-dusk/60">
          {t("session.transcript")}
        </h3>
        <div
          ref={transcriptRef}
          className="max-h-80 space-y-5 overflow-y-auto text-base leading-relaxed"
        >
          {lines.length === 0 && (
            <p className="text-shahrazad-dusk/50">{t("session.emptyTranscript")}</p>
          )}
          {transcriptBlocks.map((block, blockIndex) => (
            <div key={`${block.section}-${blockIndex}`} className="space-y-3">
              <p
                className={`text-xs font-semibold uppercase tracking-wide ${
                  block.section === "practice"
                    ? "text-shahrazad-gold"
                    : "text-shahrazad-dusk/50"
                }`}
              >
                {block.section === "practice"
                  ? t("session.practiceSection")
                  : t("session.conversationSection")}
              </p>
              {block.lines.map((line) => (
                <p
                  key={line.id}
                  className={
                    line.role === "learner" ? "text-shahrazad-dusk" : "text-shahrazad-ink"
                  }
                  dir="auto"
                >
                  <span className="text-xs font-semibold uppercase text-shahrazad-dusk/50">
                    {line.role === "learner" ? t("session.learner") : t("session.tutor")}:{" "}
                  </span>
                  {line.text}
                </p>
              ))}
            </div>
          ))}
        </div>
      </section>

      <aside className="space-y-4">
        <div className="rounded-2xl border border-shahrazad-gold/30 bg-white/80 p-4 shadow-sm">
          <h3 className="mb-3 font-semibold">{t("review.heading")}</h3>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-shahrazad-dusk/70">{t("session.practiceCount")}</span>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  disabled={drillActive}
                  onClick={() => setPracticeSentenceCount(n)}
                  aria-pressed={practiceSentenceCount === n}
                  className={`h-7 w-7 rounded-full text-xs font-semibold disabled:opacity-40 ${
                    practiceSentenceCount === n
                      ? "bg-shahrazad-dusk text-white"
                      : "border border-shahrazad-dusk/25 text-shahrazad-dusk hover:bg-white"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          {errors.length === 0 ? (
            <p className="text-sm text-shahrazad-dusk/60">{t("session.noErrors")}</p>
          ) : (
            <ul className="max-h-[420px] space-y-3 overflow-y-auto">
              {errors.map((err) => (
                <li
                  key={err.id}
                  className="rounded-lg border border-shahrazad-gold/20 bg-shahrazad-sand/50 p-3 text-sm"
                  dir="auto"
                >
                  <p className="text-xs uppercase text-shahrazad-dusk/50">{err.kind}</p>
                  <p className="line-through opacity-70">{err.learner_text}</p>
                  <p className="font-medium text-shahrazad-ink">{err.correct_form}</p>
                  <p className="mt-1 text-shahrazad-dusk/80">{err.explanation_ar}</p>
                  {err.explanation_en && err.explanation_en !== err.explanation_ar && (
                    <p className="mt-1 text-xs text-shahrazad-dusk/70">{err.explanation_en}</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2">
                    <audio controls preload="none" src={ttsUrl(err.correct_form)} className="h-8 max-w-full" />
                    <button
                      type="button"
                      onClick={() => startDrill(err.id)}
                      disabled={drillActive || Boolean(err.resolved_at)}
                      className="rounded-full border border-shahrazad-dusk/30 px-3 py-1 text-xs hover:bg-white disabled:opacity-40"
                    >
                      {drillActive ? t("session.practicing") : t("session.practiceDrill")}
                    </button>
                    <button
                      type="button"
                      onClick={() => acknowledgeError(err.id).then(refreshErrors)}
                      className="rounded-full border border-shahrazad-dusk/30 px-3 py-1 text-xs hover:bg-white"
                    >
                      {t("review.acknowledge")}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <Link
          href={`/${locale}`}
          className="block rounded-xl border border-shahrazad-dusk/20 py-3 text-center text-sm hover:bg-white/60"
        >
          {t("session.endSession")}
        </Link>
      </aside>
    </div>
  );
}

export default function LiveSessionRoom({
  config,
  locale,
}: {
  config: LiveConfig;
  locale: string;
}) {
  return (
    <LiveKitRoom
      token={config.token}
      serverUrl={config.serverUrl}
      connect
      audio
      video={false}
      className="lk-room-container"
    >
      <RoomAudioRenderer />
      <SessionInner sessionId={config.sessionId} locale={locale} />
    </LiveKitRoom>
  );
}
