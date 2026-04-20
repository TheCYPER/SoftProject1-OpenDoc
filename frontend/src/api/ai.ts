import api, { authorizedFetch } from "./client";
import type {
  AIHistoryResponse,
  AIJobCreatePayload,
  AIJobResponse,
  AISuggestion,
  AIStreamJobStartedEvent,
  AIStreamTerminalEvent,
  AIStreamTextDeltaEvent,
} from "../types";

type BackendStreamEventName = "job" | "delta" | "suggestion" | "status";

type StreamHandlers = {
  onStarted?: (payload: AIStreamJobStartedEvent) => void;
  onDelta?: (payload: AIStreamTextDeltaEvent) => void;
  onCompleted?: (payload: AIStreamTerminalEvent) => void;
  onError?: (payload: AIStreamTerminalEvent) => void;
  onCancelled?: (payload: AIStreamTerminalEvent) => void;
};

export async function streamAIJob(
  documentId: string,
  payload: AIJobCreatePayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await authorizedFetch(`/api/documents/${documentId}/ai-jobs/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    let message = `AI request failed (${response.status})`;
    try {
      const data = await response.json();
      message = data.detail ?? message;
    } catch {
      // Ignore body parse failures and keep the generic message.
    }
    throw new Error(message);
  }

  if (!response.body) {
    throw new Error("AI streaming response body was empty.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let latestSuggestion: AISuggestion | null = null;
  let jobStarted = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex >= 0) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const eventNameMatch = rawEvent.match(/^event:\s*(.+)$/m);
      const dataMatch = rawEvent.match(/^data:\s*(.+)$/m);
      if (eventNameMatch && dataMatch) {
        const eventName = eventNameMatch[1].trim() as BackendStreamEventName;
        const payloadData = JSON.parse(dataMatch[1]);
        if (eventName === "job") {
          jobStarted = true;
          handlers.onStarted?.({
            job_id: payloadData.job_id,
            suggestion_id: "",
            status: payloadData.status,
            action: payload.action,
            stale: false,
            provider_name: payloadData.provider_name ?? null,
            model_name: payloadData.model_name ?? null,
            original_text: payload.selected_text,
          });
        } else if (eventName === "delta") {
          handlers.onDelta?.({
            job_id: payloadData.job_id,
            suggestion_id: latestSuggestion?.suggestion_id ?? "",
            seq: 0,
            delta: payloadData.delta,
          });
        } else if (eventName === "suggestion") {
          latestSuggestion = payloadData as AISuggestion;
        } else if (eventName === "status") {
          const terminalPayload: AIStreamTerminalEvent = {
            job_id: payloadData.job_id,
            suggestion_id: latestSuggestion?.suggestion_id ?? "",
            status: payloadData.status,
            stale: latestSuggestion?.stale,
            text: latestSuggestion?.suggested_text ?? undefined,
            code: payloadData.error_code ?? undefined,
            message: payloadData.error_message ?? undefined,
            partial_text: latestSuggestion?.suggested_text ?? undefined,
            partial_output_available: latestSuggestion?.partial_output_available,
          };
          if (payloadData.status === "ready" || payloadData.status === "stale") {
            handlers.onCompleted?.(terminalPayload);
          } else if (payloadData.status === "cancelled") {
            handlers.onCancelled?.(terminalPayload);
          } else if (payloadData.status === "failed" || payloadData.status === "quota_exceeded") {
            handlers.onError?.(terminalPayload);
          }
        }
      }
      separatorIndex = buffer.indexOf("\n\n");
    }
  }

  if (!jobStarted) {
    throw new Error("AI stream ended before the job started.");
  }
}

export async function cancelAIJob(jobId: string): Promise<AIJobResponse> {
  const response = await api.post(`/api/ai-jobs/${jobId}/cancel`);
  return response.data;
}

export async function applyAIJob(
  jobId: string,
  mode: "full" | "partial",
  targetRevisionId?: string | null,
  selectedDiffBlocks?: number[],
): Promise<{ status: string; suggestion_id: string }> {
  const response = await api.post(`/api/ai-jobs/${jobId}/apply`, {
    mode,
    target_revision_id: targetRevisionId ?? undefined,
    selected_diff_blocks: selectedDiffBlocks,
  });
  return response.data;
}

export async function rejectAIJob(jobId: string): Promise<{ status: string }> {
  const response = await api.post(`/api/ai-jobs/${jobId}/reject`);
  return response.data;
}

export async function fetchAIHistory(documentId: string): Promise<AIHistoryResponse> {
  const response = await api.get(`/api/documents/${documentId}/ai-history`);
  return response.data;
}

export async function fetchAISuggestion(jobId: string): Promise<AISuggestion> {
  const response = await api.get(`/api/ai-jobs/${jobId}/suggestion`);
  return response.data;
}
