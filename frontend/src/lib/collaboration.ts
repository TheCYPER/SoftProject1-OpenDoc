import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";

const MESSAGE_SYNC = 0;

export type ConnectionState = "connecting" | "connected" | "disconnected";

interface CollaborationClientOptions {
  documentId: string;
  token: string;
  ydoc: Y.Doc;
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

  constructor(options: CollaborationClientOptions) {
    this.documentId = options.documentId;
    this.token = options.token;
    this.ydoc = options.ydoc;
    this.onStatusChange = options.onStatusChange;
    this.handleDocumentUpdate = this.handleDocumentUpdate.bind(this);
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
      this.sendSyncStep1();
    };

    websocket.onmessage = (event) => {
      const message = event.data;
      if (!(message instanceof ArrayBuffer)) {
        return;
      }

      const decoder = decoding.createDecoder(new Uint8Array(message));
      const messageType = decoding.readVarUint(decoder);
      if (messageType !== MESSAGE_SYNC) {
        return;
      }

      const encoder = encoding.createEncoder();
      encoding.writeVarUint(encoder, MESSAGE_SYNC);
      syncProtocol.readSyncMessage(decoder, encoder, this.ydoc, this.originToken);
      const reply = encoding.toUint8Array(encoder);
      if (reply.length > 1) {
        this.websocket?.send(reply);
      }
    };

    websocket.onerror = () => {
      websocket.close();
    };

    websocket.onclose = () => {
      this.ydoc.off("update", this.handleDocumentUpdate);
      if (this.websocket === websocket) {
        this.websocket = null;
      }
      if (this.destroyed) {
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
