import * as awarenessProtocol from "y-protocols/awareness";
import type { Awareness } from "y-protocols/awareness";
import type { DecorationAttrs } from "@tiptap/pm/view";

export interface CollaborationUserState {
  id?: string;
  name?: string;
  color?: string;
  label?: string;
}

export interface Collaborator {
  clientId: number;
  id: string;
  name: string;
  color: string;
  label: string;
}

export function colorFromSeed(seed: string): string {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  const r = 96 + (hash & 0x5f);
  const g = 96 + ((hash >> 8) & 0x5f);
  const b = 96 + ((hash >> 16) & 0x5f);
  return `#${[r, g, b].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

export function buildLocalCollaborationUser(
  name: string,
  userId?: string,
): Required<CollaborationUserState> {
  const id = userId ?? name;
  const color = colorFromSeed(id);
  return {
    id,
    name,
    color,
    label: name,
  };
}

export function normalizeCollaborator(
  clientId: number,
  state: Record<string, unknown>,
): Collaborator {
  const user = (state?.user ?? {}) as CollaborationUserState;
  const id = user.id ?? String(clientId);
  const name = user.name ?? `User ${clientId}`;
  const color = user.color ?? colorFromSeed(id);
  return {
    clientId,
    id,
    name,
    color,
    label: user.label ?? name,
  };
}

export function collectCollaborators(awareness: Awareness): Collaborator[] {
  const collaborators: Collaborator[] = [];
  awareness.getStates().forEach((state: Record<string, unknown>, clientId: number) => {
    if (clientId === awareness.clientID) return;
    collaborators.push(normalizeCollaborator(clientId, state));
  });
  return collaborators;
}

export function pruneCollaboratorsByUserId(awareness: Awareness, userId: string): void {
  const clientIds: number[] = [];
  awareness.getStates().forEach((state: Record<string, unknown>, clientId: number) => {
    if (clientId === awareness.clientID) return;
    const user = (state?.user ?? {}) as CollaborationUserState;
    if (user.id === userId) {
      clientIds.push(clientId);
    }
  });
  if (clientIds.length > 0) {
    awarenessProtocol.removeAwarenessStates(awareness, clientIds, "presence_leave");
  }
}

export function clearRemoteCollaborators(awareness: Awareness): void {
  const clientIds = collectCollaborators(awareness).map((collaborator) => collaborator.clientId);
  if (clientIds.length > 0) {
    awarenessProtocol.removeAwarenessStates(awareness, clientIds, "connection_reset");
  }
}

export function cursorBuilder(user: CollaborationUserState, clientId: number): HTMLElement {
  const collaborator = normalizeCollaborator(clientId, { user });
  const caret = document.createElement("span");
  caret.className = "remote-cursor";
  caret.style.setProperty("--cursor-color", collaborator.color);

  const label = document.createElement("span");
  label.className = "remote-cursor__label";
  label.textContent = collaborator.label;
  label.style.backgroundColor = collaborator.color;
  caret.append(label);
  return caret;
}

export function selectionBuilder(
  user: CollaborationUserState,
  clientId: number,
): DecorationAttrs {
  const collaborator = normalizeCollaborator(clientId, { user });
  return {
    class: "remote-selection",
    style: `--cursor-color: ${collaborator.color};`,
  };
}
