import axios from "axios";
import { EditorContent, useEditor } from "@tiptap/react";
import { yDocToProsemirrorJSON, ySyncPlugin, ySyncPluginKey, yUndoPlugin, yUndoPluginKey } from "y-prosemirror";
import Placeholder from "@tiptap/extension-placeholder";
import StarterKit from "@tiptap/starter-kit";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";
import api from "../api/client";
import AIPanel, { type UndoRequest } from "../components/AIPanel";
import PresenceBar from "../components/PresenceBar";
import ShareModal from "../components/ShareModal";
import VersionPanel from "../components/VersionPanel";
import { getAccessToken } from "../lib/auth";
import { CollaborationClient, type ConnectionState } from "../lib/collaboration";
import type { Document as DocType, EditorSelectionRange, ProseMirrorDoc, ProseMirrorNode, User } from "../types";

const EMPTY_DOC: ProseMirrorDoc = { type: "doc", content: [] };
const AUTO_SAVE_DEBOUNCE_MS = 3000;

type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

function formatRelativeTime(date: Date): string {
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function nodeHasRichFormatting(node: ProseMirrorNode): boolean {
  if (node.type !== "paragraph" && node.type !== "text" && node.type !== "doc") {
    return true;
  }
  if (node.marks && node.marks.length > 0) {
    return true;
  }
  return node.content?.some(nodeHasRichFormatting) ?? false;
}

function plainTextToDoc(text: string): ProseMirrorDoc {
  return {
    type: "doc",
    content: text.split("\n").map((line) => ({
      type: "paragraph",
      content: line ? [{ type: "text", text: line }] : [],
    })),
  };
}

interface AuditEvent {
  audit_event_id: string;
  event_type: string;
  target_ref: string | null;
  actor_user_id: string;
  created_at: string;
  metadata_json: Record<string, unknown> | null;
}

function wordCount(doc: ProseMirrorDoc): number {
  const text = JSON.stringify(doc);
  const matches = text.match(/"text":"([^"]*)"/g);
  if (!matches) return 0;
  return matches.reduce((sum, m) => {
    const content = m.slice(8, -1);
    return sum + content.split(/\s+/).filter(Boolean).length;
  }, 0);
}

export default function EditorPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<DocType | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [editSeq, setEditSeq] = useState(0);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [awareness, setAwareness] = useState<Awareness | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [words, setWords] = useState(0);
  const savedSnapshotRef = useRef(JSON.stringify(EMPTY_DOC));
  const ydocRef = useRef<Y.Doc | null>(null);
  const collaborationClientRef = useRef<CollaborationClient | null>(null);
  const activeDocumentIdRef = useRef<string | null>(null);
  const canEdit = doc?.role == null ? true : doc.role !== "viewer";

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        history: false,
      }),
      Placeholder.configure({
        placeholder: "Start writing here...",
      }),
    ],
    content: EMPTY_DOC,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: "rich-editor__content",
      },
    },
    onUpdate: ({ editor: nextEditor }) => {
      const json = nextEditor.getJSON() as ProseMirrorDoc;
      const dirty = JSON.stringify(json) !== savedSnapshotRef.current;
      setIsDirty(dirty);
      setWords(wordCount(json));
      if (dirty) setEditSeq((n) => n + 1);
    },
  });

  useEffect(() => {
    loadDocument();
    api.get("/api/me").then((r) => setCurrentUser(r.data)).catch(() => {});
  }, [documentId]);

  useEffect(() => {
    if (!editor) return;
    const token = getAccessToken();
    if (!token || !documentId || doc?.document_id !== documentId) {
      return;
    }
    if (activeDocumentIdRef.current === documentId && collaborationClientRef.current && ydocRef.current) {
      return;
    }

    // Create an empty Yjs document — the server will provide the authoritative
    // state via the sync protocol when the WebSocket connects.
    const ydoc = new Y.Doc();
    const yXmlFragment = ydoc.getXmlFragment("prosemirror");

    ydocRef.current?.destroy();
    ydocRef.current = ydoc;

    collaborationClientRef.current?.destroy();

    editor.unregisterPlugin([ySyncPluginKey, yUndoPluginKey]);
    editor.registerPlugin(ySyncPlugin(yXmlFragment));
    editor.registerPlugin(yUndoPlugin());

    savedSnapshotRef.current = JSON.stringify(EMPTY_DOC);
    setIsDirty(false);
    activeDocumentIdRef.current = documentId;

    const client = new CollaborationClient({
      documentId,
      token,
      ydoc,
      displayName: currentUser?.display_name ?? "User",
      onStatusChange: setConnectionState,
    });
    collaborationClientRef.current = client;
    setAwareness(client.awareness);
    client.connect();

    return () => {
      collaborationClientRef.current?.destroy();
      collaborationClientRef.current = null;
      setAwareness(null);
      editor.unregisterPlugin([ySyncPluginKey, yUndoPluginKey]);
      ydocRef.current?.destroy();
      ydocRef.current = null;
      activeDocumentIdRef.current = null;
    };
  }, [editor, documentId, doc?.document_id, currentUser?.display_name]);

  useEffect(() => {
    if (!editor) return;
    editor.setEditable(canEdit);
  }, [editor, canEdit]);

  const loadDocument = async () => {
    try {
      const resp = await api.get(`/api/documents/${documentId}`);
      setDoc(resp.data);
    } catch {
      navigate("/documents");
    }
  };

  const reloadFromServer = () => {
    // Force Yjs re-initialization — destroys old Yjs doc and reconnects to
    // get the latest authoritative state from the server.
    activeDocumentIdRef.current = null;
    collaborationClientRef.current?.destroy();
    collaborationClientRef.current = null;
    if (ydocRef.current) {
      editor?.unregisterPlugin([ySyncPluginKey, yUndoPluginKey]);
      ydocRef.current.destroy();
      ydocRef.current = null;
    }
    loadDocument();
  };

  const saveDocument = useCallback(async () => {
    if (!canEdit) return;
    setSaveStatus("saving");
    setSaveError(null);
    try {
      const nextContent = (ydocRef.current
        ? (yDocToProsemirrorJSON(ydocRef.current) as ProseMirrorDoc)
        : ((editor?.getJSON() as ProseMirrorDoc | undefined) ?? EMPTY_DOC));
      const response = await api.patch(`/api/documents/${documentId}`, { content: nextContent });
      savedSnapshotRef.current = JSON.stringify(nextContent);
      setDoc(response.data);
      setIsDirty(false);
      setLastSavedAt(new Date());
      setSaveStatus("saved");
    } catch (err) {
      const msg = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.message
        : "Save failed";
      setSaveError(msg);
      setSaveStatus("error");
    }
  }, [canEdit, documentId, editor]);

  const saveDocumentRef = useRef(saveDocument);
  useEffect(() => {
    saveDocumentRef.current = saveDocument;
  }, [saveDocument]);

  useEffect(() => {
    if (editSeq === 0 || !isDirty || !canEdit) return;
    setSaveStatus((prev) => (prev === "saving" ? prev : "dirty"));
    const timer = window.setTimeout(() => {
      void saveDocumentRef.current();
    }, AUTO_SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [editSeq, isDirty, canEdit]);

  const handleExport = async (format: "html" | "txt") => {
    setExportMenuOpen(false);
    try {
      const resp = await api.get(`/api/documents/${documentId}/export?format=${format}`, {
        responseType: "blob",
      });
      const ext = format === "html" ? "html" : "txt";
      const filename = `${doc?.title ?? "document"}.${ext}`;
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Export failed.");
    }
  };

  const loadAudit = async () => {
    setAuditLoading(true);
    try {
      const resp = await api.get(`/api/documents/${documentId}/audit`);
      setAuditEvents(resp.data);
      setAuditOpen(true);
    } catch {
      alert("Unable to load audit trail. Only document owners can view this.");
    } finally {
      setAuditLoading(false);
    }
  };

  const getSelection = (): { selectedText: string; range: EditorSelectionRange } | null => {
    if (!editor) return null;
    const { from, to, empty } = editor.state.selection;
    if (empty) return null;
    const selectedText = editor.state.doc.textBetween(from, to, "\n");
    return { selectedText, range: { from, to } };
  };

  const handleApply = (
    newText: string,
    selection?: EditorSelectionRange
  ): { ok: boolean; error?: string } => {
    if (!editor) {
      return { ok: false, error: "Editor is not ready yet." };
    }
    if (!canEdit) {
      return { ok: false, error: "You only have viewer access for this document." };
    }

    if (selection) {
      editor.chain().focus().insertContentAt(selection, newText).run();
      return { ok: true };
    }

    const currentDoc = (editor.getJSON() as ProseMirrorDoc | undefined) ?? EMPTY_DOC;
    if (nodeHasRichFormatting(currentDoc)) {
      return {
        ok: false,
        error:
          "Full-document AI apply is disabled for formatted content right now. Apply to a selection to preserve formatting.",
      };
    }

    editor.commands.setContent(plainTextToDoc(newText));
    return { ok: true };
  };

  const handleUndo = (req: UndoRequest): { ok: boolean; error?: string } => {
    if (!editor) {
      return { ok: false, error: "Editor is not ready yet." };
    }
    if (!canEdit) {
      return { ok: false, error: "You only have viewer access for this document." };
    }

    const { originalText, appliedText, selection } = req;

    if (selection) {
      // The apply replaced [selection.from, selection.to] with appliedText,
      // so its current range is [selection.from, selection.from + appliedText.length].
      const end = selection.from + appliedText.length;
      editor.chain().focus().insertContentAt({ from: selection.from, to: end }, originalText).run();
      return { ok: true };
    }

    // Whole-document apply — original selection was null, meaning the AI
    // replaced the entire doc with plain text. Restore the original plain text.
    editor.commands.setContent(plainTextToDoc(originalText));
    return { ok: true };
  };

  // Loading state
  if (!doc) {
    return (
      <div className="editor-loading">
        <div className="spinner-lg spinner" />
        <p className="text-muted" style={{ marginTop: "var(--space-md)" }}>Loading document...</p>
        <style>{`
          .editor-loading {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 60vh;
          }
        `}</style>
      </div>
    );
  }

  const connectionColor =
    connectionState === "connected" ? "var(--color-success)"
    : connectionState === "connecting" ? "var(--color-warning)"
    : "var(--text-muted)";

  return (
    <div className="editor-page">
      {/* Top bar */}
      <header className="editor-header">
        <div className="editor-header-left">
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => navigate("/documents")}
            aria-label="Back to documents"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Back
          </button>
          <div className="editor-title-group">
            <h3 className="editor-doc-title truncate">{doc.title}</h3>
            <div className="editor-status-row">
              <span
                className="editor-connection-dot"
                style={{ background: connectionColor }}
                title={connectionState}
              />
              <span className="text-xs text-muted">{connectionState}</span>
              {!canEdit && <span className="badge badge-info">Read only</span>}
              {canEdit && saveStatus === "saving" && (
                <span className="editor-save-indicator">
                  <span className="spinner" aria-hidden />
                  Saving…
                </span>
              )}
              {canEdit && saveStatus === "dirty" && (
                <span className="badge badge-warning">Unsaved</span>
              )}
              {canEdit && saveStatus === "saved" && lastSavedAt && (
                <span className="editor-save-indicator text-xs text-muted">
                  Saved {formatRelativeTime(lastSavedAt)}
                </span>
              )}
              {canEdit && saveStatus === "error" && (
                <span
                  className="badge badge-error"
                  title={saveError ?? undefined}
                >
                  Save failed — retry
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="editor-header-right">
          <PresenceBar awareness={awareness} />

          <div className="editor-actions">
            <button className="btn btn-sm" onClick={() => setShareOpen(true)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
                <polyline points="16 6 12 2 8 6"/>
                <line x1="12" y1="2" x2="12" y2="15"/>
              </svg>
              Share
            </button>
            <button className="btn btn-sm" onClick={() => setVersionsOpen(true)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              History
            </button>
            <button className="btn btn-sm" onClick={loadAudit} disabled={auditLoading}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
              Audit
            </button>

            {/* Export dropdown */}
            <div className="editor-dropdown-wrap">
              <button
                className="btn btn-sm"
                onClick={() => setExportMenuOpen(!exportMenuOpen)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Export
              </button>
              {exportMenuOpen && (
                <div className="editor-dropdown">
                  <button className="editor-dropdown-item" onClick={() => handleExport("html")}>
                    Export as HTML
                  </button>
                  <button className="editor-dropdown-item" onClick={() => handleExport("txt")}>
                    Export as Text
                  </button>
                </div>
              )}
            </div>

            <button
              className={`btn btn-sm ${saveStatus === "dirty" || saveStatus === "error" ? "btn-primary" : ""}`}
              onClick={() => void saveDocument()}
              disabled={
                !canEdit || saveStatus === "saving" || (saveStatus !== "dirty" && saveStatus !== "error")
              }
              title={saveStatus === "error" ? saveError ?? "Retry save" : undefined}
            >
              {saveStatus === "saving" && <span className="spinner" />}
              {saveStatus === "saving"
                ? "Saving..."
                : saveStatus === "error"
                  ? "Retry"
                  : saveStatus === "dirty"
                    ? "Save now"
                    : "Saved"}
            </button>
          </div>
        </div>
      </header>

      {/* Editor body */}
      <div className="editor-body">
        <div className="editor-main">
          <div className="rich-editor">
            <div className="rich-editor__toolbar">
              <button
                type="button"
                onClick={() => editor?.chain().focus().setParagraph().run()}
                disabled={!canEdit}
                className={editor?.isActive("paragraph") ? "is-active" : ""}
                title="Paragraph (Ctrl+Alt+0)"
              >
                P
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()}
                disabled={!canEdit}
                className={editor?.isActive("heading", { level: 1 }) ? "is-active" : ""}
                title="Heading 1 (Ctrl+Alt+1)"
              >
                H1
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}
                disabled={!canEdit}
                className={editor?.isActive("heading", { level: 2 }) ? "is-active" : ""}
                title="Heading 2 (Ctrl+Alt+2)"
              >
                H2
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleHeading({ level: 3 }).run()}
                disabled={!canEdit}
                className={editor?.isActive("heading", { level: 3 }) ? "is-active" : ""}
                title="Heading 3 (Ctrl+Alt+3)"
              >
                H3
              </button>
              <span className="rich-editor__sep" aria-hidden />
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleBold().run()}
                disabled={!canEdit || !editor?.can().chain().focus().toggleBold().run()}
                className={editor?.isActive("bold") ? "is-active" : ""}
                title="Bold (Ctrl+B)"
              >
                <strong>B</strong>
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleItalic().run()}
                disabled={!canEdit || !editor?.can().chain().focus().toggleItalic().run()}
                className={editor?.isActive("italic") ? "is-active" : ""}
                title="Italic (Ctrl+I)"
              >
                <em>I</em>
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleCode().run()}
                disabled={!canEdit}
                className={editor?.isActive("code") ? "is-active" : ""}
                title="Inline code (Ctrl+E)"
              >
                <code>{"</>"}</code>
              </button>
              <span className="rich-editor__sep" aria-hidden />
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleBulletList().run()}
                disabled={!canEdit}
                className={editor?.isActive("bulletList") ? "is-active" : ""}
                title="Bullet List"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/></svg>
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleOrderedList().run()}
                disabled={!canEdit}
                className={editor?.isActive("orderedList") ? "is-active" : ""}
                title="Numbered List"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/><text x="2" y="8" fontSize="8" fill="currentColor" stroke="none" fontFamily="system-ui">1</text><text x="2" y="14" fontSize="8" fill="currentColor" stroke="none" fontFamily="system-ui">2</text><text x="2" y="20" fontSize="8" fill="currentColor" stroke="none" fontFamily="system-ui">3</text></svg>
              </button>
              <span className="rich-editor__sep" aria-hidden />
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleCodeBlock().run()}
                disabled={!canEdit}
                className={editor?.isActive("codeBlock") ? "is-active" : ""}
                title="Code block (Ctrl+Alt+C)"
              >
                {"{ }"}
              </button>
            </div>
            <EditorContent editor={editor} />
          </div>

          {/* Footer bar */}
          <div className="editor-footer">
            <span className="text-xs text-muted">{words} words</span>
          </div>
        </div>

        {/* AI sidebar */}
        <div className="editor-sidebar">
          <AIPanel
            documentId={documentId!}
            editor={editor}
            getSelection={getSelection}
            onApply={handleApply}
            onUndo={handleUndo}
          />
        </div>
      </div>

      {/* Modals */}
      <ShareModal
        documentId={documentId!}
        isOpen={shareOpen}
        onClose={() => setShareOpen(false)}
      />

      <VersionPanel
        documentId={documentId!}
        isOpen={versionsOpen}
        onClose={() => setVersionsOpen(false)}
        onRestore={reloadFromServer}
      />

      {auditOpen && (
        <div className="modal-overlay" onClick={() => setAuditOpen(false)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Audit Trail</h3>
              <button className="btn btn-icon" onClick={() => setAuditOpen(false)} aria-label="Close">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div className="modal-body">
              {auditEvents.length === 0 ? (
                <p className="text-sm text-muted">No audit events recorded yet.</p>
              ) : (
                <div className="audit-list">
                  {auditEvents.map((e) => (
                    <div key={e.audit_event_id} className="audit-row">
                      <div className="audit-row-header">
                        <span className="badge badge-accent">{e.event_type}</span>
                        <span className="text-xs text-muted">
                          {new Date(e.created_at).toLocaleString()}
                        </span>
                      </div>
                      {e.target_ref && (
                        <p className="text-xs text-muted" style={{ marginTop: 4 }}>
                          Target: {e.target_ref}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <style>{`
        .editor-page {
          display: flex;
          flex-direction: column;
          min-height: 100vh;
          background: var(--bg-secondary);
        }
        .editor-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: var(--space-sm) var(--space-lg);
          background: var(--bg);
          border-bottom: 1px solid var(--border);
          position: sticky;
          top: 0;
          z-index: 20;
          gap: var(--space-md);
          flex-wrap: wrap;
        }
        .editor-header-left {
          display: flex;
          align-items: center;
          gap: var(--space-md);
          min-width: 0;
        }
        .editor-title-group {
          min-width: 0;
        }
        .editor-doc-title {
          margin: 0;
          font-size: var(--font-md);
          max-width: 300px;
        }
        .editor-status-row {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          margin-top: 2px;
        }
        .editor-connection-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .editor-save-indicator {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: var(--font-xs);
          color: var(--text-muted);
        }
        .editor-save-indicator .spinner {
          width: 10px;
          height: 10px;
        }
        .editor-header-right {
          display: flex;
          align-items: center;
          gap: var(--space-md);
        }
        .editor-actions {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          flex-wrap: wrap;
        }
        .editor-dropdown-wrap {
          position: relative;
        }
        .editor-dropdown {
          position: absolute;
          top: calc(100% + 4px);
          right: 0;
          background: var(--bg);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          box-shadow: var(--shadow-md);
          min-width: 160px;
          z-index: 30;
          overflow: hidden;
        }
        .editor-dropdown-item {
          display: block;
          width: 100%;
          text-align: left;
          padding: 8px 14px;
          border: none;
          background: none;
          color: var(--text-h);
          font-size: var(--font-sm);
          cursor: pointer;
          transition: background var(--transition);
        }
        .editor-dropdown-item:hover {
          background: var(--bg-tertiary);
        }
        .editor-body {
          display: flex;
          flex: 1;
          gap: 0;
          width: 100%;
          padding: var(--space-lg) var(--space-xl);
        }
        .editor-main {
          flex: 1;
          min-width: 0;
        }
        .editor-sidebar {
          width: 340px;
          flex-shrink: 0;
          margin-left: var(--space-lg);
        }
        @media (min-width: 1600px) {
          .editor-body {
            padding: var(--space-lg) var(--space-2xl);
          }
        }
        @media (max-width: 900px) {
          .editor-body {
            flex-direction: column;
            padding: var(--space-md);
          }
          .editor-sidebar {
            width: 100%;
            margin-left: 0;
            margin-top: var(--space-lg);
          }
          .editor-actions {
            gap: 4px;
          }
        }
        .editor-footer {
          display: flex;
          justify-content: flex-end;
          padding: var(--space-sm) var(--space-md);
        }
        .audit-list {
          display: flex;
          flex-direction: column;
          gap: var(--space-sm);
        }
        .audit-row {
          padding: var(--space-sm) 0;
          border-bottom: 1px solid var(--border);
        }
        .audit-row:last-child {
          border-bottom: none;
        }
        .audit-row-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: var(--space-sm);
        }
      `}</style>
    </div>
  );
}
