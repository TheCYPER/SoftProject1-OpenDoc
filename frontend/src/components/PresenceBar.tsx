import { useEffect, useState } from "react";
import type { Awareness } from "y-protocols/awareness";

interface Collaborator {
  clientId: number;
  name: string;
  color: string;
}

interface Props {
  awareness: Awareness | null;
}

export default function PresenceBar({ awareness }: Props) {
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);

  useEffect(() => {
    if (!awareness) return;

    const update = () => {
      const states: Collaborator[] = [];
      awareness.getStates().forEach(
        (state: Record<string, unknown>, clientId: number) => {
          if (clientId === awareness.clientID) return;
          const user = state?.user as { name?: string; color?: string } | undefined;
          const name = user?.name ?? `User ${clientId}`;
          const color = user?.color ?? hslForId(clientId);
          states.push({ clientId, name, color });
        }
      );
      setCollaborators(states);
    };

    awareness.on("change", update);
    update();
    return () => awareness.off("change", update);
  }, [awareness]);

  if (collaborators.length === 0) return null;

  const visible = collaborators.slice(0, 5);
  const overflow = collaborators.length - 5;

  return (
    <div
      className="presence-bar"
      title={collaborators.map((c) => c.name).join(", ")}
    >
      {visible.map((c) => (
        <div
          key={c.clientId}
          className="presence-avatar"
          style={{ background: c.color }}
          title={c.name}
        >
          {c.name.charAt(0).toUpperCase()}
        </div>
      ))}
      {overflow > 0 && (
        <div
          className="presence-avatar presence-overflow"
          title={`+${overflow} more`}
        >
          +{overflow}
        </div>
      )}

      <style>{`
        .presence-bar {
          display: flex;
          align-items: center;
          gap: -4px;
        }
        .presence-avatar {
          width: 32px;
          height: 32px;
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
          border: 2px solid var(--bg);
          margin-left: -6px;
          transition: transform var(--transition);
        }
        .presence-avatar:first-child {
          margin-left: 0;
        }
        .presence-avatar:hover {
          transform: scale(1.1);
          z-index: 1;
        }
        .presence-overflow {
          background: var(--bg-tertiary) !important;
          color: var(--text-muted);
          font-size: var(--font-xs);
        }
      `}</style>
    </div>
  );
}

function hslForId(id: number): string {
  return `hsl(${(id * 47) % 360}, 65%, 50%)`;
}
