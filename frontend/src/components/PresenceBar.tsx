import { useEffect, useState } from "react";
import type { Awareness } from "y-protocols/awareness";
import {
  collectCollaborators,
  type Collaborator,
} from "../lib/collaborationPresence";

interface Props {
  awareness: Awareness | null;
}

export default function PresenceBar({ awareness }: Props) {
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);

  useEffect(() => {
    if (!awareness) return;

    const update = () => {
      setCollaborators(collectCollaborators(awareness));
    };

    awareness.on("change", update);
    update();
    return () => awareness.off("change", update);
  }, [awareness]);

  if (collaborators.length === 0) return null;

  const visible = collaborators.slice(0, 4);
  const overflow = collaborators.length - 4;

  return (
    <div
      className="presence-bar"
      title={collaborators.map((c) => c.name).join(", ")}
    >
      {visible.map((c) => (
        <div
          key={c.clientId}
          className="presence-chip"
          title={c.name}
        >
          <span
            className="presence-avatar"
            style={{ background: c.color }}
            aria-hidden
          >
            {c.name.charAt(0).toUpperCase()}
          </span>
          <span className="presence-name">{c.label}</span>
        </div>
      ))}
      {overflow > 0 && (
        <div
          className="presence-chip presence-overflow"
          title={`+${overflow} more`}
        >
          +{overflow}
        </div>
      )}

      <style>{`
        .presence-bar {
          display: flex;
          align-items: center;
          gap: var(--space-xs);
          flex-wrap: wrap;
        }
        .presence-chip {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
          padding: 4px 10px 4px 4px;
          border-radius: 999px;
          border: 1px solid var(--border);
          background: var(--bg);
          color: var(--text-h);
          box-shadow: var(--shadow-sm);
        }
        .presence-avatar {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          color: #fff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: var(--font-xs);
          font-weight: 600;
          cursor: default;
          flex-shrink: 0;
          user-select: none;
        }
        .presence-name {
          max-width: 110px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: var(--font-xs);
          font-weight: 600;
        }
        .presence-overflow {
          padding: 4px 10px;
          background: var(--bg-tertiary);
          color: var(--text-muted);
          font-size: var(--font-xs);
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
