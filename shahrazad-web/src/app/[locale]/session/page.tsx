"use client";

import Link from "next/link";
import { useLocale } from "next-intl";
import { useEffect, useState } from "react";
import LiveSessionRoom from "@/components/LiveSessionRoom";

type StoredLive = {
  sessionId: string;
  token: string;
  serverUrl: string;
  topicId: string;
};

export default function SessionPage() {
  const locale = useLocale();
  const [config, setConfig] = useState<StoredLive | null>(null);

  useEffect(() => {
    const raw = sessionStorage.getItem("shahrazad-live");
    if (raw) {
      try {
        setConfig(JSON.parse(raw) as StoredLive);
      } catch {
        setConfig(null);
      }
    }
  }, []);

  if (!config) {
    return (
      <main className="mx-auto max-w-lg px-6 py-20 text-center">
        <p className="mb-4 text-shahrazad-dusk/80">No active session.</p>
        <Link href={`/${locale}`} className="text-shahrazad-gold underline">
          Choose a topic
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-4 py-8 sm:px-6">
      <header className="mb-8">
        <Link href={`/${locale}`} className="text-sm text-shahrazad-dusk/60 hover:underline">
          ← Shahrazad
        </Link>
        <p className="mt-2 text-xs text-shahrazad-dusk/50">Session {config.sessionId.slice(0, 8)}…</p>
      </header>
      <LiveSessionRoom config={config} locale={locale} />
    </main>
  );
}
