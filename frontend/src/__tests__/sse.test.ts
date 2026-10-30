import { describe, it, expect, vi } from "vitest";
import { parseSSEBuffer, streamSSE } from "../api/sse";

describe("SSE Parser (parseSSEBuffer & streamSSE)", () => {
  it("parses single standard SSE message with JSON data", () => {
    const raw = "event: token\ndata: {\"token\":\"hello\"}\n\n";
    const messages: Array<{ event: string; dataStr: string }> = [];

    const remainder = parseSSEBuffer(raw, (event, dataStr) => {
      messages.push({ event, dataStr });
    });

    expect(remainder).toBe("");
    expect(messages).toHaveLength(1);
    expect(messages[0]?.event).toBe("token");
    expect(JSON.parse(messages[0]?.dataStr || "{}")).toEqual({ token: "hello" });
  });

  it("handles chunk boundaries split across multiple chunks", () => {
    const chunk1 = "event: status\ndata: {\"mes";
    const chunk2 = "sage\": \"analyzing\"}\n\nevent: done\ndat";
    const chunk3 = "a: {}\n\n";

    const messages: Array<{ event: string; dataStr: string }> = [];

    // Process chunk 1
    let remainder = parseSSEBuffer(chunk1, (event, dataStr) => {
      messages.push({ event, dataStr });
    });
    expect(messages).toHaveLength(0);
    expect(remainder).toBe(chunk1);

    // Process chunk 2
    remainder = parseSSEBuffer(remainder + chunk2, (event, dataStr) => {
      messages.push({ event, dataStr });
    });
    expect(messages).toHaveLength(1);
    expect(messages[0]?.event).toBe("status");
    expect(JSON.parse(messages[0]?.dataStr || "{}")).toEqual({ message: "analyzing" });
    expect(remainder).toBe("event: done\ndat");

    // Process chunk 3
    remainder = parseSSEBuffer(remainder + chunk3, (event, dataStr) => {
      messages.push({ event, dataStr });
    });
    expect(messages).toHaveLength(2);
    expect(messages[1]?.event).toBe("done");
    expect(remainder).toBe("");
  });

  it("accumulates multi-line data fields into a single newline-separated payload per SSE spec", () => {
    const raw = "event: message\ndata: First line\ndata: Second line\ndata: Third line\n\n";
    const messages: Array<{ event: string; dataStr: string }> = [];

    parseSSEBuffer(raw, (event, dataStr) => {
      messages.push({ event, dataStr });
    });

    expect(messages).toHaveLength(1);
    expect(messages[0]?.dataStr).toBe("First line\nSecond line\nThird line");
  });

  it("gracefully halts streamSSE on AbortSignal", async () => {
    const controller = new AbortController();
    const onDone = vi.fn();
    const onEvent = vi.fn();

    const stream = new ReadableStream({
      start(streamController) {
        streamController.enqueue(new TextEncoder().encode("event: token\ndata: {\"token\":\"a\"}\n\n"));
      },
      pull(streamController) {
        controller.abort();
        streamController.error(new DOMException("Aborted", "AbortError"));
      },
    });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: stream,
      headers: new Headers({ "content-type": "text/event-stream" }),
    }));

    await streamSSE({
      url: "http://127.0.0.1:8000/api/v1/test-stream",
      signal: controller.signal,
      onEvent,
      onDone,
    });

    expect(onDone).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
