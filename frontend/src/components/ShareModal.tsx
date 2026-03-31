import { useEffect, useState } from "react";
import api from "../api/client";

interface Share {
  share_id: string;
  grantee_type: string;
  grantee_ref: string | null;
  role: string;
  allow_ai: boolean;
  expires_at: string | null;
  created_at: string;
}

interface Props {
  documentId: string;
  isOpen: boolean;
  onClose: () => void;
}

export default function ShareModal({ documentId, isOpen, onClose }: Props) {
  const [shares, setShares] = useState<Share[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"viewer" | "editor">("viewer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOwner, setIsOwner] = useState(true);

  useEffect(() => {
    if (isOpen) {
      setError(null);
      loadShares();
    }
  }, [isOpen, documentId]);

  const loadShares = async () => {
    try {
      const resp = await api.get(`/api/documents/${documentId}/shares`);
      setShares(resp.data);
      setIsOwner(true);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        setIsOwner(false);
        setError("Only the document owner can manage shares.");
      } else {
        setError("Failed to load shares.");
      }
    }
  };

  const addShare = async () => {
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.post(`/api/documents/${documentId}/shares`, {
        grantee_type: "USER",
        grantee_ref: email.trim(),
        role,
        allow_ai: true,
      });
      setEmail("");
      await loadShares();
    } catch {
      setError("Failed to share. Make sure the email is correct.");
    } finally {
      setLoading(false);
    }
  };

  const removeShare = async (shareId: string) => {
    try {
      await api.delete(`/api/documents/${documentId}/shares/${shareId}`);
      await loadShares();
    } catch {
      setError("Failed to remove share.");
    }
  };

  if (!isOpen) return null;

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>Share Document</h2>
          <button onClick={onClose} style={closeBtnStyle}>✕</button>
        </div>

        {error && <p style={{ color: "#c62828", marginBottom: 12, fontSize: 14 }}>{error}</p>}

        {isOwner && (
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            <input
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addShare()}
              style={inputStyle}
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as "viewer" | "editor")}
              style={{ padding: "6px 8px", borderRadius: 4, border: "1px solid #ccc" }}
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
            </select>
            <button onClick={addShare} disabled={loading || !email.trim()} style={addBtnStyle}>
              {loading ? "..." : "Add"}
            </button>
          </div>
        )}

        {shares.length === 0 ? (
          <p style={{ color: "#666", fontSize: 14 }}>No shares yet.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {shares.map((s) => (
              <li key={s.share_id} style={shareRowStyle}>
                <div>
                  <span style={{ fontWeight: 500 }}>{s.grantee_ref ?? s.grantee_type}</span>
                  <span style={roleBadgeStyle(s.role)}>{s.role}</span>
                </div>
                {isOwner && (
                  <button
                    onClick={() => removeShare(s.share_id)}
                    style={removeBtnStyle}
                    title="Remove access"
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---- styles ----------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.4)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 8,
  padding: 24,
  width: 440,
  maxWidth: "90vw",
  boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
};

const closeBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  fontSize: 18,
  cursor: "pointer",
  color: "#666",
  padding: "2px 6px",
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: "6px 10px",
  border: "1px solid #ccc",
  borderRadius: 4,
  fontSize: 14,
};

const addBtnStyle: React.CSSProperties = {
  padding: "6px 14px",
  background: "#1976d2",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 500,
};

const shareRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "8px 0",
  borderBottom: "1px solid #f0f0f0",
};

const removeBtnStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid #ccc",
  borderRadius: 4,
  padding: "3px 10px",
  cursor: "pointer",
  fontSize: 12,
  color: "#666",
};

function roleBadgeStyle(role: string): React.CSSProperties {
  const colors: Record<string, string> = {
    viewer: "#e3f2fd",
    editor: "#e8f5e9",
    admin: "#fff3e0",
  };
  return {
    marginLeft: 8,
    padding: "2px 8px",
    borderRadius: 12,
    fontSize: 12,
    background: colors[role] ?? "#f5f5f5",
    color: "#333",
  };
}
