import { useEffect, useState } from 'react'
import { ArrowUpFromLine, FileText, Network, RefreshCw, Search, Trash2, UploadCloud } from 'lucide-react'
import { api, json, type Chunk, type Document, type Translation } from '../../api/client'
import DocumentMap from './DocumentMap'

type Props = { documents: Document[]; refresh: () => Promise<void>; openPassage: (id: string) => void }

export default function DocumentsView({ documents, refresh, openPassage }: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'map' | 'text'>('map')
  const [language, setLanguage] = useState<'en' | 'hi'>('en')
  const [translations, setTranslations] = useState<Record<string, string>>({})
  const [translationBusy, setTranslationBusy] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const [uploadProgress, setUploadProgress] = useState('')
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<(Chunk & { score: number; chunk_id: string })[]>([])
  const doc = documents.find(item => item.id === selected)

  useEffect(() => {
    if (!selected) return
    api<Chunk[]>(`/documents/${selected}/chunks`).then(setChunks).catch(cause => setError(cause.message))
  }, [selected, doc?.status])

  useEffect(() => {
    if (language !== 'hi' || !selected || doc?.status !== 'ready') return
    const missing = chunks.filter(chunk => chunk.document_id === selected && chunk.page === page && !translations[chunk.id])
    if (!missing.length) return
    let cancelled = false
    setTranslationBusy(true); setTranslationError('')
    void (async () => {
      try {
        for (const passage of missing) {
          const result = await api<Translation>(`/chunks/${passage.id}/translation`)
          if (cancelled) return
          setTranslations(current => ({ ...current, [passage.id]: result.translated_text }))
        }
      } catch (cause) { if (!cancelled) setTranslationError((cause as Error).message) }
      finally { if (!cancelled) setTranslationBusy(false) }
    })()
    return () => { cancelled = true }
  }, [language, selected, doc?.status, page, chunks])

  async function upload(files: FileList | null) {
    if (!files?.length) return
    setBusy(true); setError('')
    try {
      let last: Document | null = null
      for (let index = 0; index < files.length; index++) {
        setUploadProgress(`${index + 1} of ${files.length}`)
        const body = new FormData(); body.append('file', files[index])
        const response = await api<{ document: Document; duplicate: boolean }>('/documents', { method: 'POST', body })
        last = response.document
        if (response.duplicate) setError('An identical file was already uploaded; showing the existing document.')
      }
      if (last) { setSelected(last.id); setPage(1) }
      await refresh()
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false); setUploadProgress('') }
  }

  async function replace(file: File | undefined) {
    if (!file || !doc) return
    setBusy(true); setError('')
    try {
      const body = new FormData(); body.append('file', file)
      await api(`/documents/${doc.id}`, { method: 'PUT', body })
      setPage(1); setChunks([]); setResults([]); setTranslations({}); await refresh()
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function remove() {
    if (!doc || !window.confirm(`Delete ${doc.filename} and its evidence from this knowledge base?`)) return
    setBusy(true); setError('')
    try { await api(`/documents/${doc.id}`, { method: 'DELETE' }); setSelected(null); setChunks([]); setResults([]); setTranslations({}); await refresh() }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function retry() {
    if (!doc) return
    setBusy(true); setError('')
    try { await api(`/documents/${doc.id}/retry`, { method: 'POST' }); await refresh() }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function search(event: React.FormEvent) {
    event.preventDefault(); if (!query.trim()) return
    try {
      const data = await api<{ results: typeof results }>('/search', json('POST', { query, limit: 8 }))
      setResults(data.results)
    } catch (cause) { setError((cause as Error).message) }
  }

  return <div className="page-content">
    <div className="page-heading"><div><span className="eyebrow">YOUR SOURCE LIBRARY</span><h1>Documents</h1><p>Upload reports, inspect the source, and follow each page through a simple evidence flowchart.</p></div><label className={'primary-button upload-button ' + (busy ? 'disabled' : '')}><ArrowUpFromLine size={16} />{busy ? `Uploading ${uploadProgress}…` : 'Upload reports'}<input type="file" accept=".pdf,.txt" multiple hidden disabled={busy} onChange={event => { void upload(event.target.files); event.target.value = '' }} /></label></div>
    {error && <div className="notice">{error}</div>}
    <div className="documents-grid">
      <section className="panel doc-list-panel"><div className="panel-heading"><h2>Library</h2><span className="count-badge">{documents.length}</span></div>{documents.length === 0 ? <div className="empty-state"><UploadCloud size={32} /><h3>No reports yet</h3><p>Upload a PDF or TXT report to begin.</p></div> : <div className="doc-list">{documents.map(item => <button key={item.id} className={'doc-row ' + (selected === item.id ? 'selected' : '')} onClick={() => { setSelected(item.id); setPage(1) }}><span className="doc-icon"><FileText size={20} /></span><span className="doc-row-main"><strong>{item.filename}</strong><small>{item.page_count ? `${item.page_count} ${item.page_count === 1 ? 'page' : 'pages'}` : 'Waiting for extraction'} · {item.byte_size < 1024 ? '<1' : (item.byte_size / 1024).toFixed(0)} KB</small></span><span className={'state-pill ' + item.status}>{item.status}</span></button>)}</div>}</section>
      <section className="panel doc-detail-panel">
        <div className="panel-heading"><h2>{doc ? doc.filename : 'Document preview'}</h2>{doc && <span className={'state-pill ' + doc.status}>{doc.status}</span>}</div>
        {!doc ? <div className="empty-state"><FileText size={30} /><h3>Select a report</h3><p>Its page flowchart and extracted passages will appear here.</p></div> : <>
          <div className="detail-toolbar">
            <label>Page <select value={page} onChange={event => setPage(Number(event.target.value))}>{Array.from({ length: doc.page_count || 1 }, (_, index) => <option key={index} value={index + 1}>{index + 1}</option>)}</select></label>
            <div className="document-actions">
              <button className={'view-toggle ' + (mode === 'map' ? 'active' : '')} onClick={() => setMode('map')}><Network size={14} /> Map</button>
              <button className={'view-toggle ' + (mode === 'text' ? 'active' : '')} onClick={() => setMode('text')}><FileText size={14} /> Text</button>
              <div className="language-switch" aria-label="Document language"><button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')}>English</button><button className={language === 'hi' ? 'active' : ''} onClick={() => setLanguage('hi')}>हिंदी</button></div>
              <a href={`/api/documents/${doc.id}/file#page=${page}`} target="_blank" rel="noreferrer">Original ↗</a>
            </div>
          </div>
          <div className="document-manage">
            <span>Version {doc.version} · {doc.status === 'ready' ? 'Current evidence' : 'Evidence updating'}</span>
            <details className="document-options"><summary>Manage file</summary><label className="text-button"><RefreshCw size={13} /> Replace<input type="file" accept=".pdf,.txt" hidden disabled={busy} onChange={event => { void replace(event.target.files?.[0]); event.target.value = '' }} /></label>
              {doc.status === 'failed' && <button className="text-button" onClick={() => { void retry() }}>Retry</button>}
              <button className="text-button delete-action" disabled={busy} onClick={() => { void remove() }}><Trash2 size={13} /> Delete</button></details>
          </div>
          {doc.error && doc.error !== 'AI fact suggestions unavailable until an LLM is configured' && <div className="notice">{doc.error}</div>}
          {language === 'hi' && doc.status === 'ready' && <div className={'translation-note ' + (translationError ? 'translation-error' : '')}>{translationError || (translationBusy ? 'Preparing local Hindi translation…' : 'Machine translation for reading. Original English evidence stays available.')}</div>}
          {doc.status !== 'ready' ? <div className="empty-state small"><RefreshCw size={24} /><p>{doc.status === 'failed' ? 'Processing failed. Retry or replace the file.' : 'The worker is updating this document and its evidence.'}</p></div> : mode === 'map' ?
            <DocumentMap document={doc} page={page} chunks={chunks} openPassage={openPassage} language={language} translations={translations} /> :
            <div className="page-extract"><span className="eyebrow">{language === 'hi' ? 'हिंदी अनुवाद' : 'EXTRACTED PASSAGES'} · PAGE {page}</span>{chunks.filter(chunk => chunk.page === page).length === 0 ? <p className="muted">No text is available for this page yet.</p> : chunks.filter(chunk => chunk.page === page).map(chunk => <button key={chunk.id} className="chunk-card" onClick={() => openPassage(chunk.id)}>{language === 'hi' ? <><span className="chunk-language">हिंदी · MACHINE TRANSLATION</span>{translations[chunk.id] || (translationBusy ? 'Preparing translation…' : 'Translation unavailable. Open the English source.')}<span className="original-preview">Original: {chunk.text.slice(0, 150)}{chunk.text.length > 150 ? '…' : ''}</span></> : chunk.text}<small>{chunk.id}</small></button>)}</div>}
        </>}
      </section>
    </div>
    <section className="panel search-panel"><div className="panel-heading"><div><h2>Passage search</h2><p>Find source text across all uploaded reports.</p></div></div><form className="search-form" onSubmit={event => { void search(event) }}><Search size={19} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search methods, datasets, project names…" /><button className="primary-button">Search</button></form>{results.length > 0 && <div className="results-list">{results.map(result => <button key={result.chunk_id} className="result-row" onClick={() => openPassage(result.chunk_id)}><strong>{result.filename} · page {result.page}</strong><span>{result.text}</span><small>Similarity {(result.score * 100).toFixed(0)}%</small></button>)}</div>}</section>
  </div>
}
