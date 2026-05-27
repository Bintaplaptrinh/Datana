import {
  ContextMode,
  CrawlRequest,
  JobRecord,
  ProviderInfo,
  WranglerAnalysis,
  WranglerFileContent,
  WranglerFileRecord,
} from "./types";

export const API_ROOT =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const message = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(message.detail ?? "Request failed.");
  }
  return response.json() as Promise<T>;
}

export const dataApi = {
  providers: () => request<ProviderInfo[]>("/providers"),
  jobs: () => request<JobRecord[]>("/jobs"),
  create: (payload: CrawlRequest) =>
    request<JobRecord>("/jobs", { method: "POST", body: JSON.stringify(payload) }),
  retry: (id: string) =>
    request<JobRecord>(`/jobs/${id}/retry`, { method: "POST" }),
  updateMetadata: (
    id: string,
    metadata: Record<string, string>,
    contextMode: ContextMode,
  ) =>
    request<JobRecord>(`/jobs/${id}/metadata`, {
      method: "PATCH",
      body: JSON.stringify({ metadata, context_mode: contextMode }),
    }),
  wranglerFiles: () => request<WranglerFileRecord[]>("/wrangler/files"),
  wranglerFile: (id: string) => request<WranglerFileContent>(`/wrangler/files/${id}`),
  uploadWranglerFile: (name: string, content: string) =>
    request<WranglerFileContent>("/wrangler/uploads", {
      method: "POST",
      body: JSON.stringify({ name, content }),
    }),
  saveWranglerEdit: (id: string, name: string, content: string) =>
    request<WranglerFileContent>(`/wrangler/files/${id}/edits`, {
      method: "POST",
      body: JSON.stringify({ name, content }),
    }),
  mergeWranglerFiles: (fileIds: string[], name: string) =>
    request<WranglerFileContent>("/wrangler/merges", {
      method: "POST",
      body: JSON.stringify({ file_ids: fileIds, name }),
    }),
  wranglerAnalysis: (id: string) =>
    request<WranglerAnalysis>(`/wrangler/files/${id}/analysis`),
};
