import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import * as awarenessProtocol from "y-protocols/awareness";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";
import {
  buildLocalCollaborationUser,
  clearRemoteCollaborators,
  pruneCollaboratorsByUserId,
} from "./collaborationPresence";

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;

const BASE_RETRY_MS = 1000;
const MAX_RETRY_MS = 15_000;
const JITTER_RATIO = 0.3;

const WS_CLOSE_AUTH = 4401;
const WS_CLOSE_FORBIDDEN = 4403;

export interface ConnectionStatus {
  state: "connecting" | "connected" | "disconnected" | "offline" | "forbidden";
  attempt: number;
}

interface CollaborationClientOptions {
  documentId: string;
  getToken: () => string | null;
  refreshToken?: () => Promise<boolean>;
  ydoc: Y.Doc;
  userId?: string;
  displayName?: string;
  onStatusChange: (status: ConnectionStatus) => void;
}

function buildWebSocketUrl(documentId: string, token: string): string {
  const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";
  const url = new URL(apiBase);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/documents/${documentId}`;
  url.search = new URLSearchParams({ token }).toString();
  return url.toString();
}

export class CollaborationClient {
  private readonly documentId: string;
  private readonly getToken: () => string | null;
  private readonly refreshToken?: () => Promise<boolean>;
  private readonly ydoc: Y.Doc;
  private readonly onStatusChange: (status: ConnectionStatus) => void;
  private readonly originToken = Symbol("collaboration-origin");

  private websocket: WebSocket | null = null;
  private attempt = 0;
  private reconnectTimer: number | null = null;
  private destroyed = false;
  private forbidden = false;
  private authRefreshInFlight = false;
  private onlineListener: (() => void) | null = null;

  readonly awareness: awarenessProtocol.Awareness;

  constructor(options: CollaborationClientOptions) {
    this.documentId = options.documentId;
    this.getToken = options.getToken;
    this.refreshToken = options.refreshToken;
    this.ydoc = options.ydoc;
    this.onStatusChange = options.onStatusChange;
    this.handleDocumentUpdate = this.handleDocumentUpdate.bind(this);
    this.handleAwarenessUpdate = this.handleAwarenessUpdate.bind(this);

    this.awareness = new awarenessProtocol.Awareness(options.ydoc);
    const displayName = options.displayName ?? "User";
    this.awareness.setLocalState({
      user: buildLocalCollaborationUser(displayName, options.userId),
    });
  }

  connect() {
    if (this.destroyed || this.forbidden) return;
    this.cleanupSocket();
    this.emit("connecting");

    const token = this.getToken();
    if (!token) {
      // No token available — schedule a retry; the user is likely being
      // redirected by the auth interceptor anyway.
      this.scheduleReconnect();
      return;
    }

    const websocket = new WebSocket(buildWebSocketUrl(this.documentId, token));
    websocket.binaryType = "arraybuffer";

    websocket.onopen = () => {
      this.websocket = websocket;
      this.attempt = 0;
      this.emit("connected");
      this.ydoc.on("update", this.handleDocumentUpdate);
      this.awareness.on("update", this.handleAwarenessUpdate);
      this.sendSyncStep1();
      this.broadcastAwareness();
    };

    websocket.onmessage = (event) => {
      const message = event.data;
      if (typeof message === "string") {
        this.handleControlMessage(message);
        return;
      }
      if (!(message instanceof ArrayBuffer)) {
        return;
      }

      const data = new Uint8Array(message);
      const decoder = decoding.createDecoder(data);
      const messageType = decoding.readVarUint(decoder);

      if (messageType === MESSAGE_SYNC) {
        const encoder = encoding.createEncoder();
        encoding.writeVarUint(encoder, MESSAGE_SYNC);
        syncProtocol.readSyncMessage(decoder, encoder, this.ydoc, this.originToken);
        const reply = encoding.toUint8Array(encoder);
        if (reply.length > 1) {
          this.websocket?.send(reply);
        }
      } else if (messageType === MESSAGE_AWARENESS) {
        awarenessProtocol.applyAwarenessUpdate(
          this.awareness,
          decoding.readVarUint8Array(decoder),
          this.originToken,
        );
      }
    };

    websocket.onerror = () => {
      websocket.close();
    };

    websocket.onclose = (event) => {
      void this.handleClose(event, websocket);
    };
  }

  destroy() {
    this.destroyed = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.onlineListener) {
      window.removeEventListener("online", this.onlineListener);
      this.onlineListener = null;
    }
    this.ydoc.off("update", this.handleDocumentUpdate);
    this.awareness.off("update", this.handleAwarenessUpdate);
    awarenessProtocol.removeAwarenessStates(
      this.awareness,
      [this.ydoc.clientID],
      "disconnect",
    );
    this.cleanupSocket();
    this.emit("disconnected");
  }

  /** Manual retry — cancels any scheduled reconnect and attempts immediately. */
  reconnectNow() {
    if (this.destroyed) return;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.onlineListener) {
      window.removeEventListener("online", this.onlineListener);
      this.onlineListener = null;
    }
    this.attempt = 0;
    this.forbidden = false;
    this.connect();
  }

  private async handleClose(event: CloseEvent, ws: WebSocket) {
    this.ydoc.off("update", this.handleDocumentUpdate);
    this.awareness.off("update", this.handleAwarenessUpdate);
    if (this.websocket === ws) {
      this.websocket = null;
    }
    if (this.destroyed) {
      awarenessProtocol.removeAwarenessStates(
        this.awareness,
        [this.ydoc.clientID],
        "disconnect",
      );
      return;
    }

    if (event.code === WS_CLOSE_FORBIDDEN) {
      this.forbidden = true;
      this.emit("forbidden");
      return;
    }

    // Emit a tentative "disconnected" so the UI reacts immediately;
    // scheduleReconnect may upgrade this to "offline" if appropriate.
    this.emit("disconnected");
    clearRemoteCollaborators(this.awareness);

    if (
      event.code === WS_CLOSE_AUTH &&
      this.refreshToken &&
      !this.authRefreshInFlight
    ) {
      this.authRefreshInFlight = true;
      let refreshed = false;
      try {
        refreshed = await this.refreshToken();
      } catch {
        refreshed = false;
      } finally {
        this.authRefreshInFlight = false;
      }
      if (this.destroyed) return;
      if (refreshed) {
        // Reset the backoff — we have a fresh token.
        this.attempt = 0;
        this.connect();
        return;
      }
    }

    this.scheduleReconnect();
  }

  private emit(state: ConnectionStatus["state"]) {
    this.onStatusChange({ state, attempt: this.attempt });
  }

  private handleDocumentUpdate(update: Uint8Array, origin: unknown) {
    if (origin === this.originToken || this.websocket?.readyState !== WebSocket.OPEN) {
      return;
    }
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeUpdate(encoder, update);
    this.websocket.send(encoding.toUint8Array(encoder));
  }

  private handleAwarenessUpdate(
    { added, updated, removed }: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown,
  ) {
    if (origin === this.originToken || this.websocket?.readyState !== WebSocket.OPEN) {
      return;
    }
    const changedClients = [...added, ...updated, ...removed].filter(
      (clientId) => clientId === this.ydoc.clientID,
    );
    if (changedClients.length === 0) {
      return;
    }
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
    encoding.writeVarUint8Array(
      encoder,
      awarenessProtocol.encodeAwarenessUpdate(this.awareness, changedClients),
    );
    this.websocket.send(encoding.toUint8Array(encoder));
  }

  private broadcastAwareness() {
    if (this.websocket?.readyState !== WebSocket.OPEN) return;
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
    encoding.writeVarUint8Array(
      encoder,
      awarenessProtocol.encodeAwarenessUpdate(this.awareness, [this.ydoc.clientID]),
    );
    this.websocket.send(encoding.toUint8Array(encoder));
  }

  private sendSyncStep1() {
    if (this.websocket?.readyState !== WebSocket.OPEN) {
      return;
    }
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeSyncStep1(encoder, this.ydoc);
    this.websocket.send(encoding.toUint8Array(encoder));
  }

  private scheduleReconnect() {
    if (this.destroyed || this.forbidden) return;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
    }

    // If the browser reports offline, don't spin retries against an
    // unreachable network — wait for the 'online' event instead.
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      this.emit("offline");
      this.attachOnlineListener();
      return;
    }

    this.attempt += 1;
    this.emit("disconnected");

    const base = Math.min(BASE_RETRY_MS * 2 ** (this.attempt - 1), MAX_RETRY_MS);
    const jitter = base * JITTER_RATIO * (Math.random() * 2 - 1);
    const delay = Math.max(BASE_RETRY_MS, Math.floor(base + jitter));

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private attachOnlineListener() {
    if (this.onlineListener) return;
    const onOnline = () => {
      if (this.onlineListener) {
        window.removeEventListener("online", this.onlineListener);
        this.onlineListener = null;
      }
      if (this.destroyed) return;
      this.attempt = 0;
      this.connect();
    };
    this.onlineListener = onOnline;
    window.addEventListener("online", onOnline);
  }

  private cleanupSocket() {
    const websocket = this.websocket;
    this.websocket = null;
    if (websocket && websocket.readyState < WebSocket.CLOSING) {
      websocket.close();
    }
  }

  private handleControlMessage(raw: string) {
    try {
      const payload = JSON.parse(raw) as {
        type?: string;
        user_id?: string;
        client_ids?: number[];
      };
      if (payload.type === "presence_leave") {
        if (Array.isArray(payload.client_ids) && payload.client_ids.length > 0) {
          awarenessProtocol.removeAwarenessStates(this.awareness, payload.client_ids, "presence_leave");
        } else if (payload.user_id) {
          pruneCollaboratorsByUserId(this.awareness, payload.user_id);
        }
      }
    } catch {
      // Ignore malformed control messages — they should not break sync.
    }
  }
}
