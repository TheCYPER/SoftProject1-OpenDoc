import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import * as awarenessProtocol from "y-protocols/awareness";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;

export type ConnectionState = "connecting" | "connected" | "disconnected";

interface CollaborationClientOptions {
  documentId: string;
  token: string;
  ydoc: Y.Doc;
  displayName?: string;
  onStatusChange: (status: ConnectionState) => void;
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
  private readonly token: string;
  private readonly ydoc: Y.Doc;
  private readonly onStatusChange: (status: ConnectionState) => void;
  private readonly originToken = Symbol("collaboration-origin");
  private websocket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: number | null = null;
  private destroyed = false;

  readonly awareness: awarenessProtocol.Awareness;

  constructor(options: CollaborationClientOptions) {
    this.documentId = options.documentId;
    this.token = options.token;
    this.ydoc = options.ydoc;
    this.onStatusChange = options.onStatusChange;
    this.handleDocumentUpdate = this.handleDocumentUpdate.bind(this);
    this.handleAwarenessUpdate = this.handleAwarenessUpdate.bind(this);

    this.awareness = new awarenessProtocol.Awareness(options.ydoc);
    // Set local user info
    const displayName = options.displayName ?? "User";
    const color = `hsl(${(Math.abs(hashCode(displayName)) % 360)}, 70%, 50%)`;
    this.awareness.setLocalState({ user: { name: displayName, color } });
  }

  connect() {
    this.destroyed = false;
    this.cleanupSocket();
    this.onStatusChange("connecting");

    const websocket = new WebSocket(buildWebSocketUrl(this.documentId, this.token));
    websocket.binaryType = "arraybuffer";

    websocket.onopen = () => {
      this.websocket = websocket;
      this.reconnectAttempts = 0;
      this.onStatusChange("connected");
      this.ydoc.on("update", this.handleDocumentUpdate);
      this.awareness.on("update", this.handleAwarenessUpdate);
      this.sendSyncStep1();
      this.broadcastAwareness();
    };

    websocket.onmessage = (event) => {
      const message = event.data;
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

    websocket.onclose = () => {
      this.ydoc.off("update", this.handleDocumentUpdate);
      this.awareness.off("update", this.handleAwarenessUpdate);
      if (this.websocket === websocket) {
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
      this.onStatusChange("disconnected");
      this.scheduleReconnect();
    };
  }

  destroy() {
    this.destroyed = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ydoc.off("update", this.handleDocumentUpdate);
    this.awareness.off("update", this.handleAwarenessUpdate);
    awarenessProtocol.removeAwarenessStates(
      this.awareness,
      [this.ydoc.clientID],
      "disconnect",
    );
    this.cleanupSocket();
    this.onStatusChange("disconnected");
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
    const changedClients = [...added, ...updated, ...removed];
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
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
    }
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 5000);
    this.reconnectAttempts += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private cleanupSocket() {
    const websocket = this.websocket;
    this.websocket = null;
    if (websocket && websocket.readyState < WebSocket.CLOSING) {
      websocket.close();
    }
  }
}

function hashCode(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return h;
}
