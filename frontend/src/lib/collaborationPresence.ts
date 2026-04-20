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

const CURSOR_PALETTE = [
  "#d9485f",
  "#e46f2f",
  "#c98512",
  "#1f8f6b",
  "#1f7a8c",
  "#2563eb",
  "#5b5bd6",
  "#8b5cf6",
  "#b6479d",
  "#9a3412",
  "#0f766e",
  "#475569",
];

export function colorFromSeed(seed: string): string {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return CURSOR_PALETTE[Math.abs(hash) % CURSOR_PALETTE.length];
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
  const localState = awareness.getLocalState() as Record<string, unknown> | null;
  const localUser = (localState?.user ?? {}) as CollaborationUserState;
  const localUserId = localUser.id;

  const seenIds = new Set<string>();
  const collaborators: Collaborator[] = [];
  awareness.getStates().forEach((state: Record<string, unknown>, clientId: number) => {
    if (clientId === awareness.clientID) return;
    const normalized = normalizeCollaborator(clientId, state);
    // Filter ghost-self entries: another clientID carrying our own user.id.
    // These can appear from React StrictMode's effect double-invoke (both
    // WS connections briefly register with the server) or from an
    // ungraceful reconnect before the server pruned the old awareness.
    if (localUserId && normalized.id === localUserId) return;
    // Dedupe multiple tabs for the same remote user — one chip per person.
    if (seenIds.has(normalized.id)) return;
    seenIds.add(normalized.id);
    collaborators.push(normalized);
  });
  return collaborators.sort((left, right) => (
    left.name.localeCompare(right.name) || left.clientId - right.clientId
  ));
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
