import type {
  Assessment,
  AssessmentSettings,
  AssessmentSummary,
  CheckResult,
  GenerateResult,
  GenerationRequest,
  Invite,
  InviteCreated,
  PracticeQuiz,
  Question,
  ResultAnswer,
  Result,
  TakeInfo,
  TestPaper,
} from "./types";

const TOKEN_KEY = "aap.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

/** Turn a FastAPI error body ({detail: string | [{msg}]}) into one readable sentence. */
export function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item: { msg?: string }) => (item.msg ?? "Invalid value").replace(/^Value error, /, ""))
      .join("; ");
  }
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  return `Request failed (${status}).`;
}

type Options = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit };

async function request<T>(path: string, options: Options = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = options.body;
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  }
  const response = await fetch(path, { ...options, headers, body });
  if (response.status === 401 && token && !path.startsWith("/api/take")) {
    setToken(null); // expired session: send the recruiter back to sign in
    window.location.assign("/login");
  }
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, errorMessage(response.status, data));
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const post = <T>(path: string, json?: unknown) => request<T>(path, { method: "POST", json });
const put = <T>(path: string, json: unknown) => request<T>(path, { method: "PUT", json });
const take = (token: string) => `/api/take/${encodeURIComponent(token)}`;

export const api = {
  login: (email: string, password: string) =>
    post<{ access_token: string }>("/api/auth/login", { email, password }),
  register: (email: string, password: string) =>
    post<{ access_token: string }>("/api/auth/register", { email, password }),

  listAssessments: () => request<AssessmentSummary[]>("/api/assessments"),
  createAssessment: (settings: Partial<AssessmentSettings>) => post<Assessment>("/api/assessments", settings),
  getAssessment: (id: number) => request<Assessment>(`/api/assessments/${id}`),
  updateAssessment: (id: number, settings: AssessmentSettings) =>
    put<Assessment>(`/api/assessments/${id}`, settings),
  generate: (id: number, body: GenerationRequest) =>
    post<GenerateResult>(`/api/assessments/${id}/generate`, body),
  editQuestion: (id: number, questionId: number, question: Question) =>
    put<Assessment>(`/api/assessments/${id}/questions/${questionId}`, question),
  deleteQuestion: (id: number, questionId: number) =>
    request<void>(`/api/assessments/${id}/questions/${questionId}`, { method: "DELETE" }),
  publish: (id: number) => post<Assessment>(`/api/assessments/${id}/publish`),
  listInvites: (id: number) => request<Invite[]>(`/api/assessments/${id}/invites`),
  createInvite: (id: number, body: { candidate_name: string; candidate_email: string }) =>
    post<InviteCreated>(`/api/assessments/${id}/invites`, body),

  getResult: (inviteId: number) => request<Result>(`/api/invites/${inviteId}/result`),
  overrideScore: (answerId: number, score: number, note: string) =>
    post<ResultAnswer>(`/api/answers/${answerId}/override`, { score, note }),
  async snapshotBlob(inviteId: number, snapshotId: number): Promise<Blob> {
    const response = await fetch(`/api/invites/${inviteId}/snapshots/${snapshotId}`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    });
    if (!response.ok) throw new ApiError(response.status, "Snapshot unavailable.");
    return response.blob();
  },

  takeInfo: (token: string) => request<TakeInfo>(take(token)),
  start: (token: string) => post<TestPaper>(`${take(token)}/start`, { consent: true }),
  sendEvent: (token: string, kind: string, detail = "") =>
    post<void>(`${take(token)}/events`, { kind, detail }),
  uploadSnapshot: (token: string, image: Blob) => {
    const form = new FormData();
    form.append("file", image, "snapshot.jpg");
    return request<void>(`${take(token)}/snapshots`, { method: "POST", body: form });
  },
  submit: (token: string, answers: { question_id: number; response: string }[]) =>
    post<{ status: string }>(`${take(token)}/submit`, { answers }),

  createPractice: (body: GenerationRequest) => post<PracticeQuiz>("/api/practice/quizzes", body),
  checkPractice: (quizId: string, index: number, response: string) =>
    post<CheckResult>(`/api/practice/quizzes/${quizId}/check`, { index, response }),
};
