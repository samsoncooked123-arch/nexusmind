export type Document = { id: string; filename: string; extension: string; status: string; error: string | null; page_count: number; byte_size: number; version: number; created_at: string }
export type Chunk = { id: string; document_id: string; filename?: string; page: number; ordinal: number; text: string; section: string | null }
export type Fact = { id: string; subject_id: string; subject_name: string; subject_type: string; relation: string; object_id: string; object_name: string; object_type: string; evidence_chunk_id: string; evidence_quote: string; evidence_text: string; filename: string; page: number; origin: string; polarity: 'supports' | 'denies' }
export type Topic = { id: string; label: string; status: string; documents: Pick<Document, 'id' | 'filename' | 'status'>[] }
export type GraphNode = { id: string; name: string; type: string; topics?: string[] }
export type GraphEdge = { id: string; source: string; target: string; relation: string; evidence_chunk_id: string; polarity?: 'supports' | 'denies'; evidence?: Chunk }
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] }
export type ConflictClaim = { id: string; polarity: 'supports' | 'denies'; evidence_quote: string; evidence_chunk_id: string; filename: string; page: number }
export type Conflict = { id: string; subject: string; relation: string; object: string; claims: ConflictClaim[] }
export type Answer = { answer: string; route: string; sources: (Chunk & { chunk_id: string })[]; graph_path: GraphData; insufficient_evidence: boolean; topics?: Topic[]; conflicts?: Conflict[]; language?: 'en' | 'hi'; ambiguous?: boolean; graph_unavailable?: boolean }
export type Health = { status: string; sqlite: boolean; neo4j: boolean; chroma: boolean; graph_available: boolean; graph_backend: string; llm_configured: boolean; llm_model: string | null }
export type Translation = { chunk_id?: string; source_text: string; translated_text: string; source_language: 'en'; target_language: 'hi'; engine: string; cached?: boolean }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, init)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try { detail = (await response.json()).detail || detail } catch { /* keep HTTP error */ }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}
