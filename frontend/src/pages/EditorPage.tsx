import axios from "axios";
import { EditorContent, useEditor } from "@tiptap/react";
import { prosemirrorJSONToYDoc, yDocToProsemirrorJSON, ySyncPlugin, ySyncPluginKey, yUndoPlugin, yUndoPluginKey } from "y-prosemirror";
import Placeholder from "@tiptap/extension-placeholder";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import * as Y from "yjs";
import api from "../api/client";
import AIPanel from "../components/AIPanel";
import ShareModal from "../components/ShareModal";
import { CollaborationClient, type ConnectionState } from "../lib/collaboration";
import type { Document as DocType, EditorSelectionRange, ProseMirrorDoc, ProseMirrorNode } from "../types";

const EMPTY_DOC: ProseMirrorDoc = { type: "doc", content: [] };

function isProseMirrorDoc(value: unknown): value is ProseMirrorDoc {
  return Boolean(
    value &&
      typeof value === "object" &&
      "type" in value &&
      "content" in value &&
      (value as { type?: string }).type === "doc"
  );
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

export default function EditorPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<DocType | null>(null);
  const [loadedContent, setLoadedContent] = useState<ProseMirrorDoc>(EMPTY_DOC);
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [shareOpen, setShareOpen] = useState(false);
  const savedSnapshotRef = useRef(JSON.stringify(EMPTY_DOC));
  const ydocRef = useRef<Y.Doc | null>(null);
  const collaborationClientRef = useRef<CollaborationClient | null>(null);
  const activeDocumentIdRef = useRef<string | null>(null);

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
      setIsDirty(JSON.stringify(nextEditor.getJSON()) !== savedSnapshotRef.current);
    },
  });

  useEffect(() => {
    loadDocument();
  }, [documentId]);

  useEffect(() => {
    if (!editor) return;
    const token = localStorage.getItem("token");
    if (!token || !documentId || doc?.document_id !== documentId) {
      return;
    }
    if (activeDocumentIdRef.current === documentId && collaborationClientRef.current && ydocRef.current) {
      return;
    }

    const seededDoc = prosemirrorJSONToYDoc(editor.schema, loadedContent);
    const ydoc = new Y.Doc();
    Y.applyUpdate(ydoc, Y.encodeStateAsUpdate(seededDoc));
    seededDoc.destroy();
    const yXmlFragment = ydoc.getXmlFragment("prosemirror");

    ydocRef.current?.destroy();
    ydocRef.current = ydoc;

    collaborationClientRef.current?.destroy();

    editor.unregisterPlugin([ySyncPluginKey, yUndoPluginKey]);
    editor.registerPlugin(ySyncPlugin(yXmlFragment));
    editor.registerPlugin(yUndoPlugin());

    savedSnapshotRef.current = JSON.stringify(loadedContent);
    setIsDirty(false);
    activeDocumentIdRef.current = documentId;

    const client = new CollaborationClient({
      documentId,
      token,
      ydoc,
      onStatusChange: setConnectionState,
    });
    collaborationClientRef.current = client;
    client.connect();

    return () => {
      collaborationClientRef.current?.destroy();
      collaborationClientRef.current = null;
      editor.unregisterPlugin([ySyncPluginKey, yUndoPluginKey]);
      ydocRef.current?.destroy();
      ydocRef.current = null;
      activeDocumentIdRef.current = null;
    };
  }, [editor, documentId, doc?.document_id]);

  const loadDocument = async () => {
    try {
      const resp = await api.get(`/api/documents/${documentId}`);
      setDoc(resp.data);
      const nextContent = isProseMirrorDoc(resp.data.content) ? resp.data.content : EMPTY_DOC;
      setLoadedContent(nextContent);
    } catch {
      navigate("/documents");
    }
  };

  const saveDocument = async () => {
    setSaving(true);
    try {
      const nextContent = (ydocRef.current
        ? (yDocToProsemirrorJSON(ydocRef.current) as ProseMirrorDoc)
        : ((editor?.getJSON() as ProseMirrorDoc | undefined) ?? loadedContent));
      const response = await api.patch(`/api/documents/${documentId}`, { content: nextContent });
      savedSnapshotRef.current = JSON.stringify(nextContent);
      setLoadedContent(nextContent);
      setDoc(response.data);
      setIsDirty(false);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        alert("Save failed: " + (err.response?.data?.detail || err.message));
      }
    } finally {
      setSaving(false);
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

    if (selection) {
      editor.chain().focus().insertContentAt(selection, newText).run();
      return { ok: true };
    }

    const currentDoc = (editor.getJSON() as ProseMirrorDoc | undefined) ?? loadedContent;
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

  if (!doc) return <p>Loading...</p>;

  return (
    <div style={{ maxWidth: 1000, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>{doc.title}</h1>
        <div>
          <span style={{ marginRight: 12, fontSize: 14, color: connectionState === "connected" ? "#2e7d32" : "#b26a00" }}>
            Live sync: {connectionState}
          </span>
          <button onClick={() => setShareOpen(true)} style={{ marginRight: 8 }}>
            Share
          </button>
          <button onClick={saveDocument} disabled={saving || !isDirty} style={{ marginRight: 8 }}>
            {saving ? "Saving..." : isDirty ? "Save" : "Saved"}
          </button>
          <button onClick={() => navigate("/documents")}>Back</button>
        </div>
      </div>

      <div className="rich-editor">
        <div className="rich-editor__toolbar">
          <button
            type="button"
            onClick={() => editor?.chain().focus().toggleBold().run()}
            disabled={!editor?.can().chain().focus().toggleBold().run()}
            className={editor?.isActive("bold") ? "is-active" : ""}
          >
            Bold
          </button>
          <button
            type="button"
            onClick={() => editor?.chain().focus().toggleItalic().run()}
            disabled={!editor?.can().chain().focus().toggleItalic().run()}
            className={editor?.isActive("italic") ? "is-active" : ""}
          >
            Italic
          </button>
          <button
            type="button"
            onClick={() => editor?.chain().focus().toggleBulletList().run()}
            className={editor?.isActive("bulletList") ? "is-active" : ""}
          >
            Bullet List
          </button>
          <button
            type="button"
            onClick={() => editor?.chain().focus().toggleOrderedList().run()}
            className={editor?.isActive("orderedList") ? "is-active" : ""}
          >
            Numbered List
          </button>
        </div>
        <EditorContent editor={editor} />
      </div>

      <ShareModal
        documentId={documentId!}
        isOpen={shareOpen}
        onClose={() => setShareOpen(false)}
      />

      <AIPanel
        documentId={documentId!}
        editor={editor}
        getSelection={getSelection}
        onApply={handleApply}
      />
    </div>
  );
}
