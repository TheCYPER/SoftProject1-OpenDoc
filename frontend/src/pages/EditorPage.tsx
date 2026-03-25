import axios from "axios";
import { EditorContent, useEditor } from "@tiptap/react";
import Placeholder from "@tiptap/extension-placeholder";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../api/client";
import AIPanel from "../components/AIPanel";
import type { Document as DocType } from "../types";

interface ProseMirrorNode {
  type: string;
  text?: string;
  content?: ProseMirrorNode[];
}

interface ProseMirrorDoc {
  type: "doc";
  content: ProseMirrorNode[];
}

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

  const editor = useEditor({
    extensions: [
      StarterKit,
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
  });

  useEffect(() => {
    loadDocument();
  }, [documentId]);

  useEffect(() => {
    if (!editor) return;
    editor.commands.setContent(loadedContent, false);
  }, [editor, loadedContent]);

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
      await api.patch(`/api/documents/${documentId}`, {
        content: (editor?.getJSON() as ProseMirrorDoc | undefined) ?? loadedContent,
      });
    } catch (err) {
      if (axios.isAxiosError(err)) {
        alert("Save failed: " + (err.response?.data?.detail || err.message));
      }
    } finally {
      setSaving(false);
    }
  };

  const getSelection = (): { selectedText: string; start: number; end: number } | null => {
    if (!editor) return null;
    const { from, to, empty } = editor.state.selection;
    if (empty) return null;
    const selectedText = editor.state.doc.textBetween(from, to, "\n");
    return { selectedText, start: from, end: to };
  };

  const handleApply = (newText: string, selStart?: number, selEnd?: number) => {
    if (!editor) return;

    if (selStart !== undefined && selEnd !== undefined) {
      editor.chain().focus().insertContentAt({ from: selStart, to: selEnd }, newText).run();
    } else {
      editor.commands.setContent(plainTextToDoc(newText));
    }
  };

  if (!doc) return <p>Loading...</p>;

  return (
    <div style={{ maxWidth: 1000, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>{doc.title}</h1>
        <div>
          <button onClick={saveDocument} disabled={saving} style={{ marginRight: 8 }}>
            {saving ? "Saving..." : "Save"}
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

      <AIPanel
        documentId={documentId!}
        editor={editor}
        getSelection={getSelection}
        onApply={handleApply}
      />
    </div>
  );
}
