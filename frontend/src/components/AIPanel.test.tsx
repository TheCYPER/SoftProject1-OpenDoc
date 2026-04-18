import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiPost = vi.fn();
const apiGet = vi.fn();
vi.mock("../api/client", () => ({
  default: {
    post: (...args: unknown[]) => apiPost(...args),
    get: (...args: unknown[]) => apiGet(...args),
  },
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
  onApply?: (text: string, range?: { from: number; to: number }) => { ok: boolean; error?: string };
  onUndo?: (req: UndoRequest) => { ok: boolean; error?: string };
  getSelection?: () => { selectedText: string; range: { from: number; to: number } } | null;
  editor?: Editor;
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
        onApply={onApply}
        onUndo={onUndo}
      />
    </ToastProvider>,
  );
  return { ...utils, onApply, onUndo };
}

async function runAI(user: ReturnType<typeof userEvent.setup>) {
  apiPost.mockResolvedValueOnce({ data: { job_id: "job-1" } });
  apiGet.mockResolvedValueOnce({
    data: {
      suggestion_id: "sug-1",
      original_text: "Original text goes here.",
      suggested_text: "Rewritten text here.",
      diff_json: null,
      stale: false,
      disposition: "pending",
    },
  });
  await user.click(screen.getByRole("button", { name: /run rewrite/i }));
  await screen.findByRole("heading", { name: /suggestion/i });
}

describe("AIPanel", () => {
  beforeEach(() => {
    apiPost.mockReset();
    apiGet.mockReset();
  });

  it("renders all four action buttons", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: /^rewrite$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^summarize$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^translate$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^restructure$/i })).toBeInTheDocument();
  });

  it("after running AI, shows the suggestion with Diff tab active by default", async () => {
    const user = userEvent.setup();
    renderPanel();
    await runAI(user);

    expect(screen.getByRole("tab", { name: "Diff" })).toHaveAttribute("aria-selected", "true");
    // The diff tab renders both original (struck through) and added words.
    expect(screen.getByText("Rewritten")).toBeInTheDocument(); // added
    expect(screen.getByText("Original")).toBeInTheDocument(); // deleted
  });

  it("Side-by-side tab shows original and suggestion blocks with labels", async () => {
    const user = userEvent.setup();
    renderPanel();
    await runAI(user);

    await user.click(screen.getByRole("tab", { name: /side-by-side/i }));
    expect(screen.getByText(/^Original$/i)).toBeInTheDocument();
    // The full suggestion text appears as a block (not split into diff tokens).
    expect(screen.getByText("Rewritten text here.")).toBeInTheDocument();
    expect(screen.getByText("Original text goes here.")).toBeInTheDocument();
  });

  it("Edit tab lets the user modify the suggestion; Accept passes edited text to onApply", async () => {
    const user = userEvent.setup();
    const { onApply } = renderPanel();
    await runAI(user);

    await user.click(screen.getByRole("tab", { name: "Edit" }));
    const textarea = screen.getByRole("textbox");
    expect(textarea).toHaveValue("Rewritten text here.");

    await user.clear(textarea);
    await user.type(textarea, "My custom version.");

    expect(screen.getByRole("button", { name: /accept edited/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /accept edited/i }));

    expect(onApply).toHaveBeenCalledWith("My custom version.", undefined);
    // Suggestion panel disappears after accept
    expect(screen.queryByRole("heading", { name: /suggestion/i })).not.toBeInTheDocument();
  });

  it("Accept (no edit) passes the suggested text and shows the persistent Undo banner", async () => {
    const user = userEvent.setup();
    const { onApply, container } = renderPanel();
    await runAI(user);

    await user.click(screen.getByRole("button", { name: /^accept$/i }));
    expect(onApply).toHaveBeenCalledWith("Rewritten text here.", undefined);

    const banner = container.querySelector(".ai-undo-banner") as HTMLElement | null;
    expect(banner).not.toBeNull();
    expect(within(banner!).getByText(/suggestion applied/i)).toBeInTheDocument();
    expect(within(banner!).getByRole("button", { name: /^undo$/i })).toBeInTheDocument();
  });

  it("Reject closes the suggestion without calling onApply", async () => {
    const user = userEvent.setup();
    const { onApply } = renderPanel();
    await runAI(user);

    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: /suggestion/i })).not.toBeInTheDocument();
  });

  it("Undo button calls onUndo with the original/applied text and dismisses the banner", async () => {
    const user = userEvent.setup();
    const { onApply, onUndo, container } = renderPanel();
    await runAI(user);

    await user.click(screen.getByRole("button", { name: /^accept$/i }));
    expect(onApply).toHaveBeenCalled();

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

  it("running a new AI action clears any pending Undo banner", async () => {
    const user = userEvent.setup();
    const { container } = renderPanel();
    await runAI(user);
    await user.click(screen.getByRole("button", { name: /^accept$/i }));
    expect(container.querySelector(".ai-undo-banner")).not.toBeNull();

    // Second AI run — the in-panel undo banner should clear before the new
    // suggestion arrives (the old undo would be stale).
    await runAI(user);
    expect(container.querySelector(".ai-undo-banner")).toBeNull();
  });
});
