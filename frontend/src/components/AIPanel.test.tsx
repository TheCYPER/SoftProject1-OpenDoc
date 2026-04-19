import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const streamAIJob = vi.fn();
const applyAIJob = vi.fn();
const rejectAIJob = vi.fn();
const cancelAIJob = vi.fn();
const fetchAIHistory = vi.fn();

vi.mock("../api/ai", () => ({
  streamAIJob: (...args: unknown[]) => streamAIJob(...args),
  applyAIJob: (...args: unknown[]) => applyAIJob(...args),
  rejectAIJob: (...args: unknown[]) => rejectAIJob(...args),
  cancelAIJob: (...args: unknown[]) => cancelAIJob(...args),
  fetchAIHistory: (...args: unknown[]) => fetchAIHistory(...args),
}));

import type { Editor } from "@tiptap/react";
import AIPanel, { type UndoRequest } from "./AIPanel";
import { ToastProvider } from "./Toast";

function makeEditor(text = "Original text goes here."): Editor {
  return {
    getText: () => text,
  } as unknown as Editor;
}

function renderPanel(overrides: {
  onApply?: (
    text: string,
    originalText: string,
    range?: { from: number; to: number },
  ) => { ok: boolean; error?: string };
  onUndo?: (req: UndoRequest) => { ok: boolean; error?: string };
  getSelection?: () => { selectedText: string; range: { from: number; to: number } } | null;
  editor?: Editor;
  canEdit?: boolean;
} = {}) {
  const onApply = overrides.onApply ?? vi.fn(() => ({ ok: true }));
  const onUndo = overrides.onUndo ?? vi.fn(() => ({ ok: true }));
  const getSelection = overrides.getSelection ?? (() => null);
  const editor = overrides.editor ?? makeEditor();
  const utils = render(
    <ToastProvider>
      <AIPanel
        documentId="doc-1"
        editor={editor}
        getSelection={getSelection}
        canEdit={overrides.canEdit ?? true}
        baseRevisionId="rev-1"
        onApply={onApply}
        onUndo={onUndo}
      />
    </ToastProvider>,
  );
  return { ...utils, onApply, onUndo };
}

async function runStreamingAI(user: ReturnType<typeof userEvent.setup>) {
  streamAIJob.mockImplementationOnce(async (_docId, _payload, handlers) => {
    handlers.onStarted?.({
      job_id: "job-1",
      suggestion_id: "sug-1",
      status: "streaming",
      action: "rewrite",
      stale: false,
      provider_name: "groq",
      model_name: "llama-test",
      original_text: "Original text goes here.",
    });
    handlers.onDelta?.({ job_id: "job-1", suggestion_id: "sug-1", seq: 1, delta: "Rewritten " });
    handlers.onDelta?.({ job_id: "job-1", suggestion_id: "sug-1", seq: 2, delta: "text here." });
    handlers.onCompleted?.({
      job_id: "job-1",
      suggestion_id: "sug-1",
      status: "ready",
      stale: false,
      text: "Rewritten text here.",
    });
  });
  await user.click(screen.getByRole("button", { name: /run rewrite/i }));
  await screen.findByRole("heading", { name: /suggestion/i });
}

describe("AIPanel", () => {
  beforeEach(() => {
    streamAIJob.mockReset();
    applyAIJob.mockReset();
    rejectAIJob.mockReset();
    cancelAIJob.mockReset();
    fetchAIHistory.mockReset();
    fetchAIHistory.mockResolvedValue({ items: [] });
    applyAIJob.mockResolvedValue({ status: "applied", suggestion_id: "sug-1" });
    rejectAIJob.mockResolvedValue({ status: "rejected" });
    cancelAIJob.mockResolvedValue({ job_id: "job-1", status: "cancelled" });
  });

  it("renders all four action buttons", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: /^rewrite$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^summarize$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^translate$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^restructure$/i })).toBeInTheDocument();
  });

  it("renders streamed suggestion content and Diff tab by default after completion", async () => {
    const user = userEvent.setup();
    renderPanel();
    await runStreamingAI(user);

    expect(screen.getByRole("tab", { name: "Diff" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Rewritten")).toBeInTheDocument();
    expect(screen.getByText("Original")).toBeInTheDocument();
  });

  it("accepts a streamed suggestion and records it with the backend", async () => {
    const user = userEvent.setup();
    const { onApply } = renderPanel();
    await runStreamingAI(user);

    await user.click(screen.getByRole("button", { name: /^accept$/i }));

    expect(onApply).toHaveBeenCalledWith(
      "Rewritten text here.",
      "Original text goes here.",
      undefined,
    );
    expect(applyAIJob).toHaveBeenCalledWith("job-1", "full", "rev-1");
  });

  it("rejects a streamed suggestion via the backend", async () => {
    const user = userEvent.setup();
    const { onApply } = renderPanel();
    await runStreamingAI(user);

    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    expect(rejectAIJob).toHaveBeenCalledWith("job-1");
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: /suggestion/i })).not.toBeInTheDocument();
  });

  it("supports undo after accepting a suggestion", async () => {
    const user = userEvent.setup();
    const { onUndo, container } = renderPanel();
    await runStreamingAI(user);
    await user.click(screen.getByRole("button", { name: /^accept$/i }));

    const banner = container.querySelector(".ai-undo-banner") as HTMLElement | null;
    expect(banner).not.toBeNull();
    await user.click(within(banner!).getByRole("button", { name: /^undo$/i }));

    expect(onUndo).toHaveBeenCalledWith({
      originalText: "Original text goes here.",
      appliedText: "Rewritten text here.",
      selection: null,
    });
    await waitFor(() => {
      expect(container.querySelector(".ai-undo-banner")).toBeNull();
    });
  });

  it("cancels an in-progress stream", async () => {
    const user = userEvent.setup();
    streamAIJob.mockImplementationOnce(async (_docId, _payload, handlers, signal?: AbortSignal) => {
      handlers.onStarted?.({
        job_id: "job-1",
        suggestion_id: "sug-1",
        status: "streaming",
        action: "rewrite",
        stale: false,
        provider_name: "groq",
        model_name: "llama-test",
        original_text: "Original text goes here.",
      });
      handlers.onDelta?.({ job_id: "job-1", suggestion_id: "sug-1", seq: 1, delta: "Partial output" });
      await new Promise<void>((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });

    renderPanel();
    await user.click(screen.getByRole("button", { name: /run rewrite/i }));
    await screen.findByRole("button", { name: /cancel generation/i });
    await user.click(screen.getByRole("button", { name: /cancel generation/i }));

    await waitFor(() => {
      expect(cancelAIJob).toHaveBeenCalledWith("job-1");
    });
    expect(screen.queryByRole("heading", { name: /suggestion/i })).not.toBeInTheDocument();
  });
});
