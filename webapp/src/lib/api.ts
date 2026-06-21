import type { LibraryIngestRequest, LibraryIngestResponse } from '../types/ingestion';

const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8002';

export async function submitLibrary(
  payload: LibraryIngestRequest,
): Promise<LibraryIngestResponse> {
  const res = await fetch(`${BASE}/api/libraries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}
