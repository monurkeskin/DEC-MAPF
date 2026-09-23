import { useEffect, useState } from "react";
import { request } from "./api/client";
import type { FrameSnapshot, RunDetail } from "./api/types";

const CHUNK = 32;
const MAX_CHUNKS = 8;
const MAX_BYTES = 8 * 1024 * 1024;
type Entry = { frames: FrameSnapshot[]; bytes: number };
const cache = new Map<string, Entry>();

function remember(key: string, frames: FrameSnapshot[]) {
  const bytes = new TextEncoder().encode(JSON.stringify(frames)).byteLength;
  cache.delete(key);
  // A single oversized chunk can be displayed, but is never retained in cache.
  if (bytes <= MAX_BYTES) cache.set(key, { frames, bytes });
  let total = Array.from(cache.values()).reduce((n, e) => n + e.bytes, 0);
  while (cache.size > MAX_CHUNKS || total > MAX_BYTES) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    total -= cache.get(oldest)!.bytes;
    cache.delete(oldest);
  }
}

/** Fetch only the selected chunk; stale requests are cancelled on seek/unmount. */
export function useReplayFrame(run: RunDetail | null, tick: number) {
  const id = run?.metadata.run_id;
  const count = run?.metadata.frame_count || 0;
  const target = Math.max(0, Math.min(tick, count - 1));
  const offset = Math.floor(target / CHUNK) * CHUNK;
  const key = `${id}:${offset}`;
  const [loaded, setLoaded] = useState<{
    key: string;
    frames: FrameSnapshot[];
  }>({ key: "", frames: [] });
  const [failure, setFailure] = useState<{ key: string; error: string }>({
    key: "",
    error: "",
  });
  useEffect(() => {
    if (!id || !count) return;
    const hit = cache.get(key);
    if (hit) {
      cache.delete(key);
      cache.set(key, hit);
      return;
    }
    const controller = new AbortController();
    request<{ frames: FrameSnapshot[] }>(
      `/runs/${encodeURIComponent(id)}/frames?offset=${offset}&limit=${CHUNK}`,
      { signal: controller.signal },
    )
      .then((data) => {
        if (controller.signal.aborted) return;
        remember(key, data.frames);
        setLoaded({ key, frames: data.frames });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setFailure({ key, error: String(error) });
      });
    return () => controller.abort();
  }, [id, count, offset, key]);
  const frame = (cache.get(key)?.frames ??
    (loaded.key === key ? loaded.frames : []))[target - offset];
  return {
    frame,
    loading: count > 0 && !frame,
    error: failure.key === key ? failure.error : "",
  };
}
