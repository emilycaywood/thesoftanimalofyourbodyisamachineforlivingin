// The only module that talks HTTP to the CALFLAB server.

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public stub = false,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json", "x-calflab-client": "web" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("The CALFLAB server is not reachable. Is `calflab lab` running?", 0);
  }
  if (!res.ok) {
    let message = res.statusText;
    let stub = false;
    try {
      const data = await res.json();
      message = data.error ?? data.detail ?? message;
      stub = Boolean(data.stub);
    } catch {
      /* not JSON */
    }
    throw new ApiError(String(message), res.status, stub);
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown = {}) => request<T>("POST", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  /** Run a named server command. */
  command: <T = any>(name: string, params: Record<string, unknown> = {}) =>
    request<{ result: T; revision: number; changed: string[] }>("POST", `/api/commands/${name}`, params),
  fileUrl: (rel: string) => `/api/files/${rel.split("/").map(encodeURIComponent).join("/")}`,
};
