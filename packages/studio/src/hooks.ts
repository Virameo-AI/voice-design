import { useCallback, useEffect, useMemo, useState } from "react";
import { ACTIVE, type Api, type Job, type Voice } from "./api";
import { errorMessage } from "./common";

export function useJobs(api: Api) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setJobs(await api.jobs());
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [api]);

  const busy = useMemo(() => jobs.some((j) => ACTIVE.has(j.status)), [jobs]);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), busy ? 1500 : 6000);
    return () => clearInterval(id);
  }, [refresh, busy]);

  return { jobs, refresh, error, busy };
}

export function useVoices(api: Api, jobs: Job[]) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const locked = useMemo(
    () => jobs.filter((j) => j.type === "lock" && j.status === "succeeded").length,
    [jobs],
  );

  const refresh = useCallback(async () => {
    try {
      setVoices(await api.voices());
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh, locked]);

  return { voices, refresh, error };
}
