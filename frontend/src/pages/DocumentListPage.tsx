import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import type { DocumentListItem } from "../types";

export default function DocumentListPage() {
  const navigate = useNavigate();
  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [title, setTitle] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDocs = async () => {
    try {
      const resp = await api.get("/api/documents");
      setDocs(resp.data);
    } catch {
      // If unauthorized, redirect to login
      navigate("/");
    }
  };

  const createDoc = async () => {
    if (!workspaceId.trim()) {
      alert("Enter a workspace ID first (create one or use an existing one)");
      return;
    }
    try {
      const resp = await api.post("/api/documents", {
        title: title || "Untitled",
        workspace_id: workspaceId,
      });
      navigate(`/documents/${resp.data.document_id}`);
    } catch (err) {
      console.error("Failed to create document", err);
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    navigate("/");
  };

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>My Documents</h1>
        <button onClick={logout}>Logout</button>
      </div>

      <div style={{ marginBottom: 24, display: "flex", gap: 8 }}>
        <input
          placeholder="Workspace ID"
          value={workspaceId}
          onChange={(e) => setWorkspaceId(e.target.value)}
          style={{ padding: 8, flex: 1 }}
        />
        <input
          placeholder="Document title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ padding: 8, flex: 1 }}
        />
        <button onClick={createDoc} style={{ padding: "8px 16px" }}>
          + New Document
        </button>
      </div>

      {docs.length === 0 ? (
        <p>No documents yet. Create one above.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {docs.map((doc) => (
            <li
              key={doc.document_id}
              onClick={() => navigate(`/documents/${doc.document_id}`)}
              style={{
                padding: 16,
                border: "1px solid #ddd",
                borderRadius: 8,
                marginBottom: 8,
                cursor: "pointer",
              }}
            >
              <strong>{doc.title}</strong>
              <br />
              <small>Updated: {new Date(doc.updated_at).toLocaleString()}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
