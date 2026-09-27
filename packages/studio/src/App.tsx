import { useCallback, useEffect, useMemo, useState } from "react";
import { Api, ApiError, type Favorite, type Health, type VoiceTemplate } from "./api";
import { loadToken, saveToken } from "./config";
import { errorMessage } from "./common";
import { DesignView } from "./DesignPanel";
import { VoicesView } from "./VoicesPanel";
import { JobsView } from "./JobsPanel";
import { TemplatesView } from "./TemplatesPanel";
import { ProfileView } from "./ProfilePanel";
import { useJobs, useVoices } from "./hooks";

type Tab = "design" | "voices" | "jobs" | "templates" | "profile";
type Phase = "checking" | "token" | "down" | "ready";
const TABS: { id: Tab; label: string }[] = [
  { id: "design", label: "Create" },
  { id: "voices", label: "My voices" },
  { id: "jobs", label: "Activity" },
  { id: "templates", label: "Templates" },
  { id: "profile", label: "Profile" },
];

export function App() {
  const [token, setToken] = useState(loadToken);
  const [draft, setDraft] = useState(token);
  const [phase, setPhase] = useState<Phase>("checking");
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  const probe = useCallback(async (next: string) => {
    setPhase("checking");
    setError(null);
    try {
      setHealth(await new Api(next).health());
      setPhase("ready");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(next ? "That token was rejected." : null);
        setPhase("token");
      } else {
        setError(errorMessage(err));
        setPhase("down");
      }
    }
  }, []);

  useEffect(() => {
    void probe(loadToken());
  }, [probe]);

  if (phase === "checking") return <div className="gate muted">Connecting to the voice engine…</div>;

  if (phase === "token" || phase === "down") {
    return (
      <div className="gate">
        <div className="panel pad gate-card">
          <div className="stack">
            <h1>voice design</h1>
            {phase === "down" ? (
              <>
                <p className="error">{error}</p>
                <p className="muted">
                  The page is up, and the engine behind it is not answering. Start it with <code>bun start.ts</code> from the project root.
                </p>
                <button className="primary" onClick={() => void probe(token)}>
                  Retry
                </button>
              </>
            ) : (
              <>
                <p className="muted">
                  This server requires an access token: the <code>server.token</code> value from <code>voice-generator.toml</code>.
                </p>
                <input type="password" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Access token" autoFocus />
                {error && <p className="error">{error}</p>}
                <button
                  className="primary"
                  onClick={() => {
                    saveToken(draft.trim());
                    setToken(draft.trim());
                    void probe(draft.trim());
                  }}
                  disabled={!draft.trim()}
                >
                  Continue
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <Studio
      token={token}
      initialHealth={health!}
      onForgetToken={() => {
        saveToken("");
        setToken("");
        setDraft("");
        void probe("");
      }}
    />
  );
}

function Studio({ token, initialHealth, onForgetToken }: { token: string; initialHealth: Health; onForgetToken: () => void }) {
  const api = useMemo(() => new Api(token), [token]);
  const [tab, setTab] = useState<Tab>("design");
  const [health, setHealth] = useState<Health | null>(initialHealth);
  const [selectedVoice, setSelectedVoice] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [pendingTemplate, setPendingTemplate] = useState<VoiceTemplate | null>(null);
  const { jobs, refresh, error: jobsError, busy } = useJobs(api);
  const { voices, error: voicesError } = useVoices(api, jobs);
  const favoriteIds = useMemo(() => new Set(favorites.map((item) => item.voice_id)), [favorites]);

  const refreshFavorites = useCallback(async () => {
    try {
      setFavorites(await api.favorites());
    } catch {
      setFavorites([]);
    }
  }, [api]);

  useEffect(() => {
    void refreshFavorites();
  }, [refreshFavorites, voices]);

  useEffect(() => {
    const tick = () => api.health().then(setHealth).catch(() => setHealth(null));
    const id = setInterval(tick, busy ? 3000 : 10000);
    return () => clearInterval(id);
  }, [api, busy]);

  const openVoice = useCallback((voiceId: string) => {
    setSelectedVoice(voiceId);
    setTab("voices");
  }, []);

  const useTemplate = useCallback((template: VoiceTemplate) => {
    setPendingTemplate(template);
    setTab("design");
  }, []);

  const clearPending = useCallback(() => setPendingTemplate(null), []);

  const addFavorite = useCallback(
    async (voiceId: string) => {
      await api.saveFavorite(voiceId);
      await refreshFavorites();
    },
    [api, refreshFavorites],
  );

  const removeFavorite = useCallback(
    async (voiceId: string) => {
      await api.removeFavorite(voiceId);
      await refreshFavorites();
    },
    [api, refreshFavorites],
  );

  const queued = health?.queued_jobs ?? 0;
  const activity = health ? (health.running_job ? "generating" : queued ? `${queued} queued` : "idle") : "engine not answering";
  const tone = !health ? "fail" : health.status !== "ok" ? "warn" : health.running_job ? "busy" : "ok";
  const problem = health?.error ?? jobsError ?? voicesError;

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#create" onClick={() => setTab("design")}>
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
              <path d="M4 16v3m5-9v12m5-18v24m5-17v10m5-15v20m5-13v6" />
            </svg>
          </span>
          voice design
        </a>
        <nav className="nav" aria-label="Main navigation">
          {TABS.map((item) => (
            <button key={item.id} type="button" aria-selected={tab === item.id} onClick={() => setTab(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="top-right">
          <span className={`status ${tone}`}>{activity}</span>
          <details className="engine">
            <summary>Engine</summary>
            <div>
              {health ? (
                <>
                  <p>
                    {health.backend} · {health.device}
                  </p>
                  <p>
                    {health.models_loaded.length}/2 models loaded
                    {health.models_loaded.length ? `: ${health.models_loaded.join(", ")}` : ""}
                  </p>
                </>
              ) : (
                <p>The engine is not answering.</p>
              )}
              <p>{location.host}</p>
              <a href={api.docsUrl()} target="_blank" rel="noreferrer">
                API docs
              </a>
              {token && (
                <button type="button" className="secondary" onClick={onForgetToken}>
                  Sign out
                </button>
              )}
            </div>
          </details>
        </div>
      </header>
      {problem && <div className="notice">{problem}</div>}
      {tab === "design" && (
        <DesignView
          api={api}
          jobs={jobs}
          onSubmitted={() => void refresh()}
          onLocked={openVoice}
          onOpenTemplates={() => setTab("templates")}
          pendingTemplate={pendingTemplate}
          onPendingUsed={clearPending}
          favoriteIds={favoriteIds}
          onAddFavorite={(voiceId) => void addFavorite(voiceId)}
        />
      )}
      {tab === "voices" && (
        <VoicesView
          api={api}
          voices={voices}
          jobs={jobs}
          selectedVoiceId={selectedVoice}
          onSelectVoice={setSelectedVoice}
          onSubmitted={() => void refresh()}
          favoriteIds={favoriteIds}
          onToggleFavorite={(voiceId, add) => void (add ? addFavorite(voiceId) : removeFavorite(voiceId))}
        />
      )}
      {tab === "jobs" && <JobsView api={api} jobs={jobs} onChanged={() => void refresh()} />}
      {tab === "templates" && <TemplatesView api={api} onUse={useTemplate} />}
      {tab === "profile" && (
        <ProfileView api={api} favorites={favorites} onSpeak={openVoice} onRemove={(voiceId) => void removeFavorite(voiceId)} onBrowse={() => setTab("voices")} />
      )}
    </div>
  );
}
