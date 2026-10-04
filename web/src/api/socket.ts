// Websocket event stream with automatic reconnect.
import type { LabEvent } from "./types";

type Listener = (event: LabEvent) => void;
type StatusListener = (connected: boolean) => void;

export class EventStream {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<StatusListener>();
  private retry = 500;
  private closed = false;

  connect(): void {
    this.closed = false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 500;
      this.statusListeners.forEach((l) => l(true));
    };
    ws.onmessage = (msg) => {
      let event: LabEvent;
      try {
        event = JSON.parse(msg.data as string);
      } catch {
        return;
      }
      if (event.type === "ping") return;
      this.listeners.forEach((l) => l(event));
    };
    ws.onclose = () => {
      this.statusListeners.forEach((l) => l(false));
      if (this.closed) return;
      setTimeout(() => this.connect(), this.retry);
      this.retry = Math.min(this.retry * 2, 5000);
    };
    ws.onerror = () => ws.close();
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }
}

export const events = new EventStream();
