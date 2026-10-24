import { useEffect, useRef, useState } from 'react'
import { Check, ClipboardCheck, ExternalLink, Plus, X } from 'lucide-react'
import { api, json, type Chunk, type Document, type Fact } from '../../api/client'
import './review.css'

type Props = { documents: Document[]; openPassage: (id: string) => void }
type Form = { subject: string; relation: string; object: string; chunk: string; quote: string; polarity: 'supports' | 'denies'; subjectId?: string; objectId?: string }
const blank: Form = { subject: '', relation: 'USES_METHOD', object: '', chunk: '', quote: '', polarity: 'supports' }
const objectTypes: Record<string, string> = { USES_METHOD: 'Method', EVALUATED_ON: 'Dataset', CREATED_BY: 'Organization' }

export default function ReviewView({ documents, openPassage }: Props) {
  const [facts, setFacts] = useState<Fact[]>([])
  const [selected, setSelected] = useState<Fact | null>(null)
  const [form, setForm] = useState<Form>(blank)
  const [documentId, setDocumentId] = useState('')
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const documentSelectRef = useRef<HTMLSelectElement>(null)

  async function reload() { setFacts(await api<Fact[]>('/facts/pending')) }
  useEffect(() => { void reload().catch(cause => setError(cause.message)) }, [])
  useEffect(() => { if (documentId) api<Chunk[]>(`/documents/${documentId}/chunks`).then(setChunks).catch(cause => setError(cause.message)) }, [documentId])

  function chooseFact(fact: Fact) {
    setSelected(fact); setDocumentId('')
    setForm({ subject: fact.subject_name, relation: fact.relation, object: fact.object_name,
      chunk: fact.evidence_chunk_id, quote: fact.evidence_quote, polarity: fact.polarity,
      subjectId: fact.subject_id, objectId: fact.object_id })
  }

  function startNewFact() {
    setSelected(null); setForm(blank); setDocumentId(''); setChunks([])
    window.requestAnimationFrame(() => documentSelectRef.current?.focus())
  }

  function payload() {
    return { subject: { name: form.subject, type: 'Project', id: form.subjectId || undefined },
      relation: form.relation,
      object: { name: form.object, type: objectTypes[form.relation], id: form.objectId || undefined },
      evidence_chunk_id: form.chunk, evidence_quote: form.quote, polarity: form.polarity }
  }

  async function save() {
    setBusy(true); setError('')
    try {
      if (selected) await api(`/facts/${selected.id}`, json('PATCH', payload()))
      else await api('/facts', json('POST', payload()))
      setSelected(null); setForm(blank); await reload()
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function decide(fact: Fact, action: 'approve' | 'reject') {
    setBusy(true); setError('')
    try { await api(`/facts/${fact.id}/${action}`, { method: 'POST' }); if (selected?.id === fact.id) { setSelected(null); setForm(blank) } await reload() }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  const selectedChunk = chunks.find(chunk => chunk.id === form.chunk)
  const evidenceText = selected?.evidence_text || selectedChunk?.text
  const hasUnsavedEdits = Boolean(selected && (form.subject !== selected.subject_name || form.relation !== selected.relation ||
    form.object !== selected.object_name || form.chunk !== selected.evidence_chunk_id || form.quote !== selected.evidence_quote ||
    form.polarity !== selected.polarity))

  return <div className="page-content"><div className="page-heading"><div><span className="eyebrow">HUMAN VERIFIED GRAPH</span><h1>Review facts</h1><p>Only approved relationships enter the knowledge graph. Check each quote against its source passage.</p></div><button className="secondary-button" onClick={startNewFact}><Plus size={16} /> New fact</button></div>
    {error && <div className="notice error">{error}</div>}
    <div className="claim-type-control"><label>Claim meaning <select value={form.polarity} onChange={event => setForm({ ...form, polarity: event.target.value as Form['polarity'] })}><option value="supports">Source supports this relationship</option><option value="denies">Source explicitly denies it</option></select></label><span>Denial needs an exact quote such as “does not use”.</span></div>
    <div className="review-grid"><section className="panel"><div className="panel-heading"><h2>Pending suggestions</h2><span className="count-badge">{facts.length}</span></div>{facts.length ? <div className="fact-list">{facts.map(fact => <button key={fact.id} className={'fact-row ' + (selected?.id === fact.id ? 'selected' : '')} onClick={() => chooseFact(fact)}><span className="fact-relation">{fact.relation.replaceAll('_', ' ')}</span><strong>{fact.subject_name} <span>→</span> {fact.object_name}</strong><small>{fact.filename} · page {fact.page} · {fact.origin}</small></button>)}</div> : <div className="empty-state"><ClipboardCheck size={30} /><h3>Review queue is clear</h3><p>Upload documents with an LLM configured, or add a fact manually.</p></div>}</section>
    <section className="panel editor-panel"><div className="panel-heading"><h2>{selected ? 'Inspect suggestion' : 'Add a verified fact'}</h2>{selected && <button className="text-button" onClick={startNewFact}>Clear</button>}</div><div className="form-stack">{!selected && <label>Source document<select ref={documentSelectRef} value={documentId} onChange={event => { setDocumentId(event.target.value); setForm({ ...form, chunk: '', quote: '' }) }}><option value="">Choose a document</option>{documents.filter(doc => doc.status === 'ready').map(doc => <option key={doc.id} value={doc.id}>{doc.filename}</option>)}</select></label>}<div className="form-row"><label>Project name<input value={form.subject} onChange={event => setForm({ ...form, subject: event.target.value, subjectId: undefined })} placeholder="e.g. RoadWatch" /></label><label>Relationship<select value={form.relation} onChange={event => setForm({ ...form, relation: event.target.value, objectId: undefined })}>{Object.keys(objectTypes).map(relation => <option key={relation} value={relation}>{relation.replaceAll('_', ' ')}</option>)}</select></label></div><label>{objectTypes[form.relation]} name<input value={form.object} onChange={event => setForm({ ...form, object: event.target.value, objectId: undefined })} placeholder={`Enter ${objectTypes[form.relation]?.toLowerCase()} name`} /></label>{!selected && <label>Evidence passage<select value={form.chunk} onChange={event => { const chunk = chunks.find(c => c.id === event.target.value); setForm({ ...form, chunk: event.target.value, quote: chunk?.text.slice(0, 180) || '' }) }}><option value="">Choose a passage</option>{chunks.map(chunk => <option key={chunk.id} value={chunk.id}>Page {chunk.page}: {chunk.text.slice(0, 70)}</option>)}</select></label>}<label>Exact evidence quote<textarea rows={3} value={form.quote} onChange={event => setForm({ ...form, quote: event.target.value })} placeholder="Copy a short exact quote from the passage" /></label>{evidenceText && <div className="evidence-box"><span className="eyebrow">SOURCE TEXT</span><p>{evidenceText}</p><button className="text-button" onClick={() => openPassage(form.chunk)}><ExternalLink size={14} /> View source passage</button></div>}{hasUnsavedEdits && <p className="muted">Save your edits before approving this fact.</p>}<div className="editor-actions"><button className="primary-button" disabled={busy || !form.subject || !form.object || !form.chunk || !form.quote} onClick={() => { void save() }}>{selected ? 'Save edits' : 'Add to review queue'}</button>{selected && <><button className="approve-button" disabled={busy || hasUnsavedEdits} onClick={() => { void decide(selected, 'approve') }}><Check size={16} /> Approve</button><button className="reject-button" disabled={busy} onClick={() => { void decide(selected, 'reject') }}><X size={16} /> Reject</button></>}</div></div></section></div>
  </div>
}
