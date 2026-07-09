"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchTopics, startLiveSession, type Topic } from "@/lib/api";

export default function HomePage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTopics()
      .then(setTopics)
      .catch((e) => setError(String(e)));
  }, []);

  async function onStart(topicId: string) {
    setLoading(topicId);
    setError(null);
    try {
      const live = await startLiveSession(topicId);
      sessionStorage.setItem(
        "shahrazad-live",
        JSON.stringify({
          sessionId: live.session_id,
          token: live.token,
          serverUrl: live.livekit_url,
          topicId: live.topic_id,
        }),
      );
      router.push(`/${locale}/session`);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(null);
    }
  }

  const otherLocale = locale === "ar" ? "en" : "ar";

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-6 py-12">
      <header className="mb-10 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-shahrazad-dusk">
            {locale === "ar" ? "شهرزاد" : "Shahrazad"}
          </h1>
          <p className="mt-2 text-shahrazad-dusk/80">{t("brand.subtitle")}</p>
        </div>
        <Link
          href={`/${otherLocale}`}
          className="rounded-full border border-shahrazad-gold/40 px-3 py-1 text-sm text-shahrazad-dusk hover:bg-white/60"
        >
          {otherLocale === "ar" ? "العربية" : "English"}
        </Link>
      </header>

      <h2 className="mb-6 text-xl font-medium">{t("topics.heading")}</h2>

      {error && (
        <p className="mb-4 rounded-lg bg-red-100 px-4 py-2 text-sm text-red-800">{error}</p>
      )}

      <ul className="grid gap-4">
        {topics.map((topic) => (
          <li
            key={topic.topic_id}
            className="rounded-2xl border border-shahrazad-gold/30 bg-white/70 p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-lg font-semibold">
                  {locale === "ar" ? topic.title_ar : topic.title_en}
                </p>
                <p className="text-sm text-shahrazad-dusk/70">
                  {t("topics.level")}: {topic.level_hint}
                </p>
              </div>
              <button
                type="button"
                disabled={loading !== null}
                onClick={() => onStart(topic.topic_id)}
                className="rounded-full bg-shahrazad-dusk px-5 py-2 text-sm font-medium text-shahrazad-sand transition hover:bg-shahrazad-ink disabled:opacity-50"
              >
                {loading === topic.topic_id ? "…" : t("topics.start")}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
