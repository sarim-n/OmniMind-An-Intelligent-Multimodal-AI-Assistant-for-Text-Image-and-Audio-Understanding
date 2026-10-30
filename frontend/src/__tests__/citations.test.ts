import { describe, it, expect } from "vitest";
import {
  parseMessageCitations,
  timestampToSeconds,
  formatSecondsToTime,
} from "../utils/citations";

describe("Multimodal Citation Parser", () => {
  it("converts timestamps to seconds and formats back", () => {
    expect(timestampToSeconds("01:23")).toBe(83);
    expect(timestampToSeconds("00:00")).toBe(0);
    expect(timestampToSeconds("01:10:05")).toBe(4205);
    expect(formatSecondsToTime(83)).toBe("01:23");
    expect(formatSecondsToTime(0)).toBe("00:00");
  });

  it("parses single audio citation with timestamp", () => {
    const text = "As stated in [audio:interview.wav 02:15], the deadline is Friday.";
    const segments = parseMessageCitations(text);

    expect(segments).toHaveLength(3);
    expect(segments[0]).toEqual({ type: "text", content: "As stated in " });
    expect(segments[1]).toEqual({
      type: "citation",
      citation: {
        type: "audio",
        target: "interview.wav",
        timestampSec: 135,
        timestampFormatted: "02:15",
        raw: "[audio:interview.wav 02:15]",
      },
    });
    expect(segments[2]).toEqual({ type: "text", content: ", the deadline is Friday." });
  });

  it("parses single image citation", () => {
    const text = "The architectural blueprint is shown in [image:blueprint.png].";
    const segments = parseMessageCitations(text);

    expect(segments).toHaveLength(3);
    expect(segments[0]).toEqual({ type: "text", content: "The architectural blueprint is shown in " });
    expect(segments[1]).toEqual({
      type: "citation",
      citation: {
        type: "image",
        target: "blueprint.png",
        raw: "[image:blueprint.png]",
      },
    });
    expect(segments[2]).toEqual({ type: "text", content: "." });
  });

  it("parses multiple mixed audio and image citations in one response", () => {
    const text =
      "Check [image:diagram.png] and listen to [audio:kickoff.wav 00:45] followed by [audio:review.m4a 12:30].";
    const segments = parseMessageCitations(text);

    const citations = segments.filter((s) => s.type === "citation");
    expect(citations).toHaveLength(3);

    const c0 = citations[0]?.citation;
    if (c0 && c0.type === "image") {
      expect(c0.target).toBe("diagram.png");
    }

    const c1 = citations[1]?.citation;
    if (c1 && c1.type === "audio") {
      expect(c1.target).toBe("kickoff.wav");
      expect(c1.timestampSec).toBe(45);
    }

    const c2 = citations[2]?.citation;
    if (c2 && c2.type === "audio") {
      expect(c2.target).toBe("review.m4a");
      expect(c2.timestampSec).toBe(750);
    }
  });

  it("returns single text segment when no citations are present", () => {
    const text = "This is a regular assistant response with no bracketed citations.";
    const segments = parseMessageCitations(text);

    expect(segments).toHaveLength(1);
    expect(segments[0]).toEqual({ type: "text", content: text });
  });
});
