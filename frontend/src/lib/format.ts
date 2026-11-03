import type { QuestionType } from "../types";

/** 75 -> "1:15", 3725 -> "1:02:05". */
export function formatClock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "-";
}

export function formatScore(score: number | null, max: number | null): string {
  if (score === null || max === null) return "-";
  return `${+score.toFixed(1)} / ${max}`;
}

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  published: "Published",
  invited: "Invited",
  in_progress: "In progress",
  submitted: "Grading",
  graded: "Graded",
  needs_review: "Needs review",
  expired: "Expired",
  timed_out: "Timed out",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export const TYPE_LABELS: Record<QuestionType, string> = {
  mcq: "Multiple choice",
  short_answer: "Short answer",
  coding: "Coding",
};

/** Comma-separated skills input -> clean list. */
export function parseSkills(text: string): string[] {
  return text
    .split(",")
    .map((skill) => skill.trim())
    .filter(Boolean);
}

export const EVENT_LABELS: Record<string, string> = {
  tab_hidden: "Left the tab",
  tab_visible: "Returned to the tab",
  window_blur: "Window lost focus",
  fullscreen_exit: "Exited full screen",
  copy: "Copied text",
  paste: "Pasted text",
  camera_unavailable: "Camera unavailable",
};
