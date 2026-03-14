const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://100.127.246.60:8000";

export interface ManualAnswer {
  summary: string;
  steps: string[];
  pages_referenced: string[];
}

export interface QueryResponse {
  answer: ManualAnswer;
}

export async function queryManual(
  question: string,
  images: File[] = []
): Promise<ManualAnswer> {
  const form = new FormData();
  form.append("question", question);
  for (const img of images) {
    form.append("images", img);
  }

  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  const data: QueryResponse = await res.json();
  return data.answer;
}
