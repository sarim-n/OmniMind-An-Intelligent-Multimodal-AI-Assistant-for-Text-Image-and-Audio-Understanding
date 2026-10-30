import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Composer } from "../components/Composer";
import { ToastProvider } from "../context/ToastContext";

describe("Composer Component & Validation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Stub URL.createObjectURL and revokeObjectURL
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:mock-url"),
      revokeObjectURL: vi.fn(),
    });
  });

  const renderWithToast = (ui: React.ReactElement) => {
    return render(<ToastProvider>{ui}</ToastProvider>);
  };

  it("submits prompt when Enter is pressed without Shift", async () => {
    const onSend = vi.fn();
    renderWithToast(<Composer onSend={onSend} isStreaming={false} />);

    const textarea = screen.getByPlaceholderText(/Ask anything/i);
    fireEvent.change(textarea, { target: { value: "Hello assistant!" } });

    // Press Enter
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend).toHaveBeenCalledWith(
        expect.objectContaining({
          content: "Hello assistant!",
          images: [],
        })
      );
    });
  });

  it("does NOT submit prompt when Shift+Enter is pressed (inserts newline)", () => {
    const onSend = vi.fn();
    renderWithToast(<Composer onSend={onSend} isStreaming={false} />);

    const textarea = screen.getByPlaceholderText(/Ask anything/i);
    fireEvent.change(textarea, { target: { value: "Line one" } });

    // Press Shift+Enter
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("disables send button when input is empty and no attachments exist", () => {
    const onSend = vi.fn();
    renderWithToast(<Composer onSend={onSend} isStreaming={false} />);

    const sendButton = screen.getByRole("button", { name: /Send/i });
    expect(sendButton).toBeDisabled();
  });

  it("rejects image attachments with unsupported mime types or extensions", async () => {
    const onSend = vi.fn();
    const { container } = renderWithToast(<Composer onSend={onSend} isStreaming={false} />);

    // Find image file input
    const imageInput = container.querySelector('input[type="file"][accept="image/*"]') as HTMLInputElement;
    expect(imageInput).toBeInTheDocument();

    const invalidFile = new File(["dummy text content"], "document.txt", { type: "text/plain" });

    fireEvent.change(imageInput, { target: { files: [invalidFile] } });

    await waitFor(() => {
      // Toast message should indicate invalid image type
      expect(screen.getByText(/Invalid image type/i)).toBeInTheDocument();
    });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("rejects files exceeding size limit (>20MB)", async () => {
    const onSend = vi.fn();
    const { container } = renderWithToast(<Composer onSend={onSend} isStreaming={false} />);

    const imageInput = container.querySelector('input[type="file"][accept="image/*"]') as HTMLInputElement;

    // File with simulated size of 25MB
    const largeFile = new File(["dummy content"], "large_photo.png", { type: "image/png" });
    Object.defineProperty(largeFile, "size", { value: 25 * 1024 * 1024 });

    fireEvent.change(imageInput, { target: { files: [largeFile] } });

    await waitFor(() => {
      expect(screen.getByText(/Image too large/i)).toBeInTheDocument();
    });
  });

  it("handles denied microphone permission gracefully without crashing", async () => {
    const onSend = vi.fn();

    // Mock getUserMedia rejecting with NotAllowedError
    const getUserMediaMock = vi.fn().mockRejectedValue(
      Object.assign(new Error("Permission denied"), { name: "NotAllowedError" })
    );

    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: getUserMediaMock },
      configurable: true,
      writable: true,
    });

    renderWithToast(<Composer onSend={onSend} isStreaming={false} />);

    const micButton = screen.getByTitle(/Record speech/i);
    fireEvent.click(micButton);

    await waitFor(() => {
      expect(screen.getAllByText(/Microphone access was denied/i).length).toBeGreaterThanOrEqual(1);
    });
  });
});
