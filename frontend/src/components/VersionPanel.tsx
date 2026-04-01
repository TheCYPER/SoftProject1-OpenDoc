import { useEffect, useState } from "react";
import api from "../api/client";

interface Version {
  version_id: string;
  document_id: string;
  base_revision_id: string | null;
  reason: string | null;
  created_by: string;
  restored_from_version_id: string | null;
  created_at: string;
}

interface Props {
  documentId: string;
  isOpen: boolean;
  onClose: () => void;
  onRestore: () => void;
}

const REASON_BADGE: Record<string, string> = {
  initial: "badge-info",
  update: "badge-success",
  restore: "badge-warning",
  ai_apply: "badge-accent",
};

export default function VersionPanel({ documentId, isOpen, onClose, onRestore }: Props) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadVersions();
    }
  }, [isOpen, documentId]);

  const loadVersions = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get(`/api/documents/${documentId}/versions`);
      setVersions(resp.data);
    } catch {
      setError("Failed to load versions.");
    } finally {
      setLoading(false);
    }
  };

  const restore = async (versionId: string) => {
    setRestoring(versionId);
    setError(null);
    try {
      await api.post(`/api/documents/${documentId}/versions/${versionId}/restore`);
      onRestore();
      onClose();
    } catch {
      setError("Failed to restore version.");
    } finally {
      setRestoring(null);
    }
  };

  if (!isOpen) return null;

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleString();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Version History</h3>
          <button className="btn btn-icon" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div className="modal-body">
          {error && <div className="alert alert-error" style={{ marginBottom: "var(--space-md)" }}>{error}</div>}

          {loading && (
            <div style={{ textAlign: "center", padding: "var(--space-lg)" }}>
              <span className="spinner-lg spinner" />
            </div>
          )}

          {!loading && versions.length === 0 && (
            <p className="text-sm text-muted" style={{ textAlign: "center", padding: "var(--space-lg)" }}>
              No versions recorded yet.
            </p>
          )}

          {!loading && versions.length > 0 && (
            <div className="version-list">
              {versions.map((v, idx) => {
                const isCurrent = idx === 0;
                return (
                  <div
                    key={v.version_id}
                    className={`version-row ${isCurrent ? "version-current" : ""}`}
                  >
                    <div className="version-dot" />
                    <div className="version-content">
                      <div className="version-title-row">
                        <span className="font-medium text-sm" style={{ color: "var(--text-h)" }}>
                          {isCurrent ? "Current Version" : `Version ${versions.length - idx}`}
                        </span>
                        <div className="version-badges">
                          {v.reason && (
                            <span className={`badge ${REASON_BADGE[v.reason] ?? "badge-muted"}`}>
                              {v.reason}
                            </span>
                          )}
                          {v.restored_from_version_id && (
                            <span className="badge badge-warning">restored</span>
                          )}
                        </div>
                      </div>
                      <span className="text-xs text-muted">{formatDate(v.created_at)}</span>
                    </div>
                    {!isCurrent && (
                      <button
                        className="btn btn-sm"
                        onClick={() => restore(v.version_id)}
                        disabled={restoring === v.version_id}
                      >
                        {restoring === v.version_id ? <span className="spinner" /> : "Restore"}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <style>{`
        .version-list {
          display: flex;
          flex-direction: column;
        }
        .version-row {
          display: flex;
          align-items: center;
          gap: var(--space-md);
          padding: var(--space-sm) 0;
          position: relative;
        }
        .version-row:not(:last-child)::before {
          content: '';
          position: absolute;
          left: 5px;
          top: 28px;
          bottom: -8px;
          width: 2px;
          background: var(--border);
        }
        .version-dot {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: var(--border);
          flex-shrink: 0;
          z-index: 1;
        }
        .version-current .version-dot {
          background: var(--accent);
          box-shadow: 0 0 0 3px var(--accent-bg);
        }
        .version-content {
          flex: 1;
          min-width: 0;
        }
        .version-title-row {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
          flex-wrap: wrap;
        }
        .version-badges {
          display: flex;
          gap: 4px;
        }
      `}</style>
    </div>
  );
}
