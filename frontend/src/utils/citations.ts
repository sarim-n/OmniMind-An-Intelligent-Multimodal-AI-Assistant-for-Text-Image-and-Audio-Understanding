/**
 * Utilities to detect and parse multimodal inline citations:
 *   [audio:<filename_or_id> mm:ss]
 *   [image:<filename_or_id>]
 */

export interface AudioCitation {
  type: "audio";
  target: string;
  timestampSec: number;
  timestampFormatted: string;
  raw: string;
}

export interface ImageCitation {
  type: "image";
  target: string;
  raw: string;
}

export type Citation = AudioCitation | ImageCitation;

export type MessageSegment =
  | { type: "text"; content: string }
  | { type: "citation"; citation: Citation };

/**
 * Converts formatted string "mm:ss" or "hh:mm:ss" into integer seconds.
 */
export function timestampToSeconds(ts: string): number {
  const parts = ts.trim().split(":").map(Number);
  if (parts.some(isNaN)) return 0;
  if (parts.length === 2) {
    const [min, sec] = parts;
    return (min ?? 0) * 60 + (sec ?? 0);
  }
  if (parts.length === 3) {
    const [hr, min, sec] = parts;
    return (hr ?? 0) * 3600 + (min ?? 0) * 60 + (sec ?? 0);
  }
  return 0;
}

/**
 * Formats seconds into "mm:ss" string.
 */
export function formatSecondsToTime(sec: number): string {
  if (isNaN(sec) || sec < 0) return "00:00";
  const total = Math.floor(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

const CITATION_REGEX = /\[(audio|image):([^\]]+)\]/g;

/**
 * Parses markdown/text content into alternating text blocks and clickable citation tokens.
 */
export function parseMessageCitations(text: string): MessageSegment[] {
  if (!text) return [];

  const segments: MessageSegment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = CITATION_REGEX.exec(text)) !== null) {
    const matchStart = match.index;
    const matchEnd = CITATION_REGEX.lastIndex;

    // Push preceding text segment if any
    if (matchStart > lastIndex) {
      segments.push({
        type: "text",
        content: text.slice(lastIndex, matchStart),
      });
    }

    const kind = match[1];
    const payload = (match[2] ?? "").trim();
    const raw = match[0];

    if (kind === "audio") {
      // Audio payload format: "<filename_or_id> <timestamp>"
      const spaceIdx = payload.lastIndexOf(" ");
      let target = payload;
      let timestampFormatted = "00:00";
      let timestampSec = 0;

      if (spaceIdx !== -1) {
        target = payload.slice(0, spaceIdx).trim();
        timestampFormatted = payload.slice(spaceIdx + 1).trim();
        timestampSec = timestampToSeconds(timestampFormatted);
      }

      segments.push({
        type: "citation",
        citation: {
          type: "audio",
          target,
          timestampSec,
          timestampFormatted,
          raw,
        },
      });
    } else if (kind === "image") {
      // Image payload format: "<filename_or_id>"
      segments.push({
        type: "citation",
        citation: {
          type: "image",
          target: payload,
          raw,
        },
      });
    }

    lastIndex = matchEnd;
  }

  // Push remainder text
  if (lastIndex < text.length) {
    segments.push({
      type: "text",
      content: text.slice(lastIndex),
    });
  }

  return segments;
}
