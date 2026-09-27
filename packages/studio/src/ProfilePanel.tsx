import type { Api, Favorite } from "./api";
import { SoundClip } from "./SoundClip";

export function ProfileView({
  api,
  favorites,
  onSpeak,
  onRemove,
  onBrowse,
}: {
  api: Api;
  favorites: Favorite[];
  onSpeak: (voiceId: string) => void;
  onRemove: (voiceId: string) => void;
  onBrowse: () => void;
}) {
  return (
    <section className="view" aria-label="Profile">
      <div className="subhero">
        <span className="eyebrow">Your voice studio / 05</span>
        <h1>
          Voices you want <em>in front.</em>
        </h1>
        <p className="lead">A short shelf of the locked voices you plan to use again. Removing one from here leaves it in My voices.</p>
      </div>
      {favorites.length === 0 ? (
        <section className="panel pad">
          <p className="muted empty">Your profile is empty.</p>
          <button type="button" className="secondary" onClick={onBrowse}>
            Browse My voices
          </button>
        </section>
      ) : (
        <div className="template-grid">
          {favorites.map((voice) => (
            <article key={voice.voice_id} className="template-card">
              <div className="template-load static">
                <span className="tiny-tag">Profile</span>
                <strong>{voice.name}</strong>
                <span>
                  {voice.language} · seed {voice.seed ?? "none"}
                </span>
              </div>
              <SoundClip
                api={api}
                path={api.voiceFilePath(voice.voice_id, "master.wav")}
                filename={`${voice.voice_id}-master.wav`}
                label={`${voice.name} reference clip`}
                seed={voice.seed}
              />
              {voice.profile_note && <p className="muted small">{voice.profile_note}</p>}
              <div className="template-actions">
                <button type="button" className="primary" onClick={() => onSpeak(voice.voice_id)}>
                  Speak
                </button>
                <button type="button" className="secondary" onClick={() => onRemove(voice.voice_id)}>
                  Remove from profile
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
