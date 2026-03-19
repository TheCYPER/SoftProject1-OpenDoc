import axios from "axios";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../api/client";
import AIPanel from "../components/AIPanel";
import type { Document as DocType } from "../types";

export default function EditorPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<DocType | null>(null);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    loadDocument();
  }, [documentId]);

  const loadDocument = async () => {
    try {
      const resp = await api.get(`/api/documents/${documentId}`);
      setDoc(resp.data);
      const content = resp.data.content;
      if (content?.content) {
        const parts = content.content
          .flatMap((node: Record<string, unknown>) =>
            (node.content as Array<Record<string, unknown>> || [])
              .filter((c) => c.type === "text")
              .map((c) => c.text as string)
          );
        setText(parts.join("\n"));
      }
    } catch {
      navigate("/documents");
    }
  };

  const saveDocument = async () => {
    setSaving(true);
    try {
      const content = {
        type: "doc",
        content: text.split("\n").map((line) => ({
          type: "paragraph",
          content: line ? [{ type: "text", text: line }] : [],
        })),
      };
      await api.patch(`/api/documents/${documentId}`, { content });
    } catch (err) {
      if (axios.isAxiosError(err)) {
        alert("Save failed: " + (err.response?.data?.detail || err.message));
      }
    } finally {
      setSaving(false);
    }
  };

  const getSelection = (): { selectedText: string; start: number; end: number } | null => {
    const el = textareaRef.current;
    if (!el) return null;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    if (start === end) return null; // no selection
    return { selectedText: text.slice(start, end), start, end };
  };

  const handleApply = (newText: string, selStart?: number, selEnd?: number) => {
    if (selStart !== undefined && selEnd !== undefined) {
      // Replace only the selected portion
      setText(text.slice(0, selStart) + newText + text.slice(selEnd));
    } else {
      setText(newText);
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

      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        style={{
          width: "100%",
          minHeight: 400,
          padding: 16,
          fontSize: 16,
          fontFamily: "inherit",
          border: "1px solid #ddd",
          borderRadius: 8,
          resize: "vertical",
        }}
      />

      <AIPanel
        documentId={documentId!}
        text={text}
        getSelection={getSelection}
        onApply={handleApply}
      />
    </div>
  );
}
