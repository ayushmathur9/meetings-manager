export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

export interface ApiErrorCompany {
  company_id: string;
  company_name: string;
  address?: string | null;
}

export class ApiError extends Error {
  status: number;
  /** Machine-readable code for structured backend errors (e.g. "missing_coordinates"). */
  code?: string;
  /** Companies affected by the error, when the backend lists them. */
  companies: ApiErrorCompany[];
  constructor(status: number, message: string, code?: string, companies: ApiErrorCompany[] = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.companies = companies;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body && !isFormData ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let message = res.statusText;
    let code: string | undefined;
    let companies: ApiErrorCompany[] = [];
    try {
      const data = await res.json();
      const detail = data.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        // FastAPI request-validation errors
        message = detail.map((d) => String(d.msg ?? "").replace(/^Value error, /, "")).filter(Boolean).join("; ") || message;
      } else if (detail && typeof detail === "object") {
        message = detail.message || message;
        code = detail.code;
        companies = detail.companies ?? [];
      }
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message, code, companies);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<T>(path, { method: "POST", body: formData });
  },
};
