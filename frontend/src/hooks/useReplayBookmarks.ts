import { useState } from "react";
export function useReplayBookmarks() {
  const [note, setNote] = useState("");
  const [bookmarks, setBookmarks] = useState<
    Record<string, { tick: number; note: string; agent: string | null }[]>
  >(() => {
    try {
      return JSON.parse(localStorage.getItem("mapf-bookmarks") || "{}");
    } catch {
      return {};
    }
  });
  return { note, setNote, bookmarks, setBookmarks };
}
