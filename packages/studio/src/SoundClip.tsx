import { useEffect, useId, useRef, useState } from "react";
import type { Api } from "./api";
import { errorMessage } from "./common";
import { formatTime, PALETTES, paletteFor, readEnvelope, waveGeometry } from "./sound";

const listeners = new Set<(id: string) => void>();

function claim(id: string) {
  for (const listener of listeners) listener(id);
}

const envelopeCache = new Map<string, number[]>();

export function SoundClip({
  api,
  path,
  filename,
  label,
  seed,
  load = "visible",
  onPlayingChange,
}: {
  api: Api;
  path: string;
  filename: string;
  label: string;
  seed?: number | null;
  load?: "visible" | "request";
  onPlayingChange?: (playing: boolean) => void;
}) {
  const reactId = useId();
  const clipId = `${reactId}:${path}`;
  const theme = PALETTES[paletteFor(seed)];
  const rootRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const waveRef = useRef<HTMLDivElement>(null);
  const [wanted, setWanted] = useState(false);
  const [src, setSrc] = useState<string | null>(null);
  const [peaks, setPeaks] = useState<number[] | null>(envelopeCache.get(path) ?? null);
  const [error, setError] = useState<string | null>(null);
  const [fallback, setFallback] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [motion, setMotion] = useState(0);

  useEffect(() => {
    if (load !== "visible" || wanted) return;
    const node = rootRef.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setWanted(true);
    }, { rootMargin: "200px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [load, wanted]);

  useEffect(() => {
    if (!wanted) return;
    let alive = true;
    let url: string | null = null;
    setError(null);
    setFallback(false);
    api
      .blob(path)
      .then(async (blob) => {
        if (!alive) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
        const cached = envelopeCache.get(path);
        if (cached) {
          setPeaks(cached);
          return;
        }
        try {
          const next = await readEnvelope(blob);
          envelopeCache.set(path, next);
          if (alive) setPeaks(next);
        } catch {
          if (alive) setFallback(true);
        }
      })
      .catch((err) => alive && setError(errorMessage(err)));
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [api, path, wanted]);

  useEffect(() => {
    const node = waveRef.current;
    if (!node) return;
    const measure = () => setSize({ width: Math.round(node.clientWidth), height: Math.round(node.clientHeight) });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [wanted, fallback]);

  useEffect(() => {
    const onClaim = (owner: string) => {
      if (owner !== clipId) audioRef.current?.pause();
    };
    listeners.add(onClaim);
    return () => {
      listeners.delete(onClaim);
    };
  }, [clipId]);

  const notify = useRef(onPlayingChange);
  notify.current = onPlayingChange;
  useEffect(() => {
    notify.current?.(playing);
  }, [playing]);

  useEffect(() => {
    if (!playing || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const started = performance.now();
    const tick = (now: number) => {
      setMotion((now - started) * 0.0007 + 0.001);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      setMotion(0);
    };
  }, [playing]);

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      return;
    }
    claim(clipId);
    if (ended) audio.currentTime = 0;
    void audio.play();
  }

  function seekTo(seconds: number) {
    const audio = audioRef.current;
    if (!audio || !duration) return;
    audio.currentTime = Math.min(duration, Math.max(0, seconds));
    setTime(audio.currentTime);
    setEnded(false);
  }

  if (!wanted && load === "request") {
    return (
      <div className="player-request" ref={rootRef}>
        <button type="button" className="secondary" onClick={() => setWanted(true)}>
          ▶ Load {label}
        </button>
      </div>
    );
  }
  if (error) return <p className="error small">Could not load {label}: {error}</p>;

  const ready = Boolean(src && peaks);
  const { width, height } = size;
  const shape = width > 0 && height > 0 ? waveGeometry(peaks, width, height, motion) : null;
  const key = reactId.replace(/:/g, "");
  const icon = playing ? "❚❚" : ended ? "↺" : "▶";
  const action = playing ? "Pause" : ended ? "Replay" : "Play";

  return (
    <div className={playing ? "player is-playing" : "player"} ref={rootRef}>
      <button type="button" className="play" onClick={toggle} disabled={!src} aria-label={`${action} ${label}`}>
        {icon}
      </button>
      {fallback ? (
        <audio className="native" controls src={src ?? undefined} aria-label={label} />
      ) : (
        <div
          ref={waveRef}
          className={ready ? "wave" : "wave loading"}
          role="slider"
          tabIndex={ready ? 0 : -1}
          aria-label={ready ? `Seek in ${label}` : `Loading ${label}`}
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(time)}
          aria-valuetext={`${formatTime(time)} of ${formatTime(duration)}`}
          onClick={(event) => {
            if (!ready) return;
            const rect = event.currentTarget.getBoundingClientRect();
            seekTo(((event.clientX - rect.left) / rect.width) * duration);
          }}
          onKeyDown={(event) => {
            const moves: Record<string, number> = { ArrowRight: time + 2, ArrowUp: time + 2, ArrowLeft: time - 2, ArrowDown: time - 2, Home: 0, End: duration };
            const next = moves[event.key];
            if (next == null) return;
            event.preventDefault();
            seekTo(next);
          }}
        >
          {shape && (
            <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
              <defs>
                <linearGradient id={`c-${key}`}>
                  {theme.colors.map((color, index) => (
                    <stop key={`${color}-${index}`} offset={`${(index * 100) / (theme.colors.length - 1)}%`} stopColor={color} />
                  ))}
                </linearGradient>
                <filter id={`g-${key}`} x="-30%" y="-100%" width="160%" height="300%">
                  <feGaussianBlur stdDeviation="3" />
                </filter>
              </defs>
              <rect width={width} height={height} rx="10" fill="#131316" />
              <g stroke="#fff" strokeOpacity="0.13" strokeWidth="1">
                {shape.grid.map((x) => (
                  <line key={x} x1={x} x2={x} y1="7" y2={height - 7} />
                ))}
              </g>
              <path d={shape.band} fill={`url(#c-${key})`} opacity={ready ? 0.52 : 0.2} filter={`url(#g-${key})`} />
              <path d={shape.band} fill={`url(#c-${key})`} opacity={ready ? 0.26 : 0.1} />
              <g fill="none" stroke={`url(#c-${key})`} strokeWidth="1.15">
                {shape.contours.map((contour, index) => (
                  <path key={index} d={contour.d} opacity={(contour.strong ? 0.9 : 0.68) * (ready ? 1 : 0.4)} />
                ))}
              </g>
              <line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke="#fff" strokeWidth="5" opacity="0.42" filter={`url(#g-${key})`} />
              <line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke="#fff8ef" strokeWidth="1.6" opacity="0.95" />
            </svg>
          )}
        </div>
      )}
      <div className="player-meta">
        <span className="duration" aria-hidden="true">
          {ready || fallback ? `${formatTime(time)} / ${formatTime(duration)}` : "Loading…"}
        </span>
        <a className="download" href={src ?? undefined} download={filename} aria-disabled={!src} aria-label={`Download ${label} as WAV`}>
          ↓ Download WAV
        </a>
      </div>
      <audio
        ref={audioRef}
        src={src ?? undefined}
        preload="metadata"
        hidden
        onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
        onPlay={() => {
          setPlaying(true);
          setEnded(false);
        }}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false);
          setEnded(true);
        }}
      />
    </div>
  );
}
