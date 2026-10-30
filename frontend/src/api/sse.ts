/**
 * Server-Sent Events (SSE) streaming parser for POST fetch requests.
 * Compliant with WHATWG SSE specification: handles chunk boundaries,
 * multi-line data fields, custom event names, and AbortController signals.
 */

export interface SSEEvent<T = any> { // eslint-disable-line @typescript-eslint/no-explicit-any
  event: string;
  data: T;
  raw: string;
}

export interface StreamSSEOptions {
  url: string;
  headers?: Record<string, string>;
  body?: BodyInit;
  method?: string;
  signal?: AbortSignal;
  onEvent: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
}

/**
 * Parses raw SSE text buffer into complete messages and remaining unparsed chunk.
 */
export function parseSSEBuffer(
  buffer: string,
  onMessage: (event: string, dataStr: string, raw: string) => void
): string {
  // Normalize \r\n to \n
  const normalized = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const messages = normalized.split("\n\n");

  // The last element is potentially incomplete
  const remainder = messages.pop() ?? "";

  for (const rawMessage of messages) {
    if (!rawMessage.trim()) continue;

    let eventType = "message";
    const dataLines: string[] = [];

    const lines = rawMessage.split("\n");
    for (const line of lines) {
      if (line.startsWith(":")) {
        // SSE comment, ignore
        continue;
      }
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        // Per spec: strip single leading space if present
        let val = line.slice(5);
        if (val.startsWith(" ")) {
          val = val.slice(1);
        }
        dataLines.push(val);
      }
    }

    const dataStr = dataLines.join("\n");
    onMessage(eventType, dataStr, rawMessage);
  }

  return remainder;
}

/**
 * Perform a streaming fetch and emit parsed SSE events.
 */
export async function streamSSE(options: StreamSSEOptions): Promise<void> {
  const { url, headers = {}, body, method = "POST", signal, onEvent, onError, onDone } = options;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: "text/event-stream",
        ...headers,
      },
      body,
      signal,
    });
  } catch (err: unknown) {
    if (signal?.aborted) {
      onDone?.();
      return;
    }
    const error = err instanceof Error ? err : new Error(String(err));
    onError?.(error);
    throw error;
  }

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    const error = new Error(errorDetail);
    onError?.(error);
    throw error;
  }

  if (!response.body) {
    throw new Error("Response body is null, cannot stream SSE");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      buffer = parseSSEBuffer(buffer, (event, dataStr, raw) => {
        let parsedData: any = dataStr; // eslint-disable-line @typescript-eslint/no-explicit-any
        try {
          parsedData = JSON.parse(dataStr);
        } catch {
          // Keep as string if not valid JSON
        }
        onEvent({ event, data: parsedData, raw });
      });
    }

    // Flush any leftover in buffer
    if (buffer.trim()) {
      parseSSEBuffer(buffer + "\n\n", (event, dataStr, raw) => {
        let parsedData: any = dataStr; // eslint-disable-line @typescript-eslint/no-explicit-any
        try {
          parsedData = JSON.parse(dataStr);
        } catch {
          // Keep as string
        }
        onEvent({ event, data: parsedData, raw });
      });
    }

    onDone?.();
  } catch (err: unknown) {
    if (signal?.aborted) {
      onDone?.();
      return;
    }
    const error = err instanceof Error ? err : new Error(String(err));
    onError?.(error);
    throw error;
  } finally {
    reader.releaseLock();
  }
}
