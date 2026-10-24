import { useCallback, useEffect, useRef, useState } from 'react'
import { BookOpen, Database, GitBranch, Languages, Layers3, MessageSquareText, X } from 'lucide-react'
import { api, type Chunk, type Document, type Health, type Translation } from './api/client'
import DocumentsView from './features/documents/DocumentsView'
import ReviewView from './features/review/ReviewView'
import ExploreView from './features/graph/ExploreView'
import AskView from './features/chat/AskView'

type Tab = 'documents' | 'review' | 'explore' | 'ask'
const tabs: { id: Tab; label: string; icon: typeof BookOpen }[] = [
  { id: 'documents', label: 'Documents', icon: BookOpen },
  { id: 'review', label: 'Review facts', icon: Layers3 },
  { id: 'explore', label: 'Explore graph', icon: GitBranch },
  { id: 'ask', label: 'Ask NexusMind', icon: MessageSquareText },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('documents')
  const [health, setHealth] = useState<Health | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [passage, setPassage] = useState<Chunk | null>(null)
  const activePassageId = useRef<string | null>(null)
  const [passageTranslation, setPassageTranslation] = useState('')
  const [showPassageTranslation, setShowPassageTranslation] = useState(false)
  const [translatingPassage, setTranslatingPassage] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [nextHealth, nextDocuments] = await Promise.all([api<Health>('/health'), api<Document[]>('/documents')])
      setHealth(nextHealth)
      setDocuments(nextDocuments)
      setError('')
    } catch (cause) { setError((cause as Error).message) }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const openPassage = useCallback(async (chunkId: string) => {
    activePassageId.current = chunkId
    try { setPassageTranslation(''); setShowPassageTranslation(false); setTranslationError('');
      setTranslatingPassage(false)
      const next = await api<Chunk>('/chunks/' + encodeURIComponent(chunkId))
      if (activePassageId.current === chunkId) setPassage(next) }
    catch (cause) { setError((cause as Error).message) }
  }, [])

  async function showHindiPassage() {
    if (!passage) return
    const chunkId = passage.id
    if (passageTranslation) { setShowPassageTranslation(true); return }
    setTranslatingPassage(true); setTranslationError('')
    try {
      const result = await api<Translation>(`/chunks/${chunkId}/translation`)
      if (activePassageId.current === chunkId) { setPassageTranslation(result.translated_text); setShowPassageTranslation(true) }
    } catch (cause) { if (activePassageId.current === chunkId) setTranslationError((cause as Error).message) }
    finally { if (activePassageId.current === chunkId) setTranslatingPassage(false) }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Database size={20} /></span><span><strong>NEXUSMIND</strong><small>Connected knowledge</small></span></div>
      <div className="sidebar-label">WORKSPACE</div>
      <nav aria-label="Main navigation">{tabs.map(item => <button key={item.id} className={'nav-item ' + (tab === item.id ? 'active' : '')} onClick={() => setTab(item.id)}><item.icon size={18} />{item.label}</button>)}</nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-footer"><div className={'status-dot ' + (health?.status === 'ok' ? 'online' : 'warning')} /><span>{health?.graph_available ? `Graph: ${health.graph_backend === 'sqlite' ? 'SQLite local' : 'Neo4j'}` : health?.graph_available === false ? 'Graph service offline' : 'Connecting to services'}</span></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="breadcrumb">Workspace <span>/</span> <strong>{tabs.find(item => item.id === tab)?.label}</strong></div><div className="topbar-right"><span className="doc-count">{documents.length} documents</span>{health?.llm_configured && <span className="mini-status ready">AI: {health.llm_model}</span>}</div></header>
      {error && <div className="global-error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss"><X size={16} /></button></div>}
      {tab === 'documents' && <DocumentsView documents={documents} refresh={refresh} openPassage={openPassage} />}
      {tab === 'review' && <ReviewView documents={documents} openPassage={openPassage} />}
      {tab === 'explore' && <ExploreView documents={documents} openPassage={openPassage} />}
      {tab === 'ask' && <AskView openPassage={openPassage} />}
    </main>
    {passage && <div className="drawer-backdrop" onMouseDown={() => { activePassageId.current = null; setPassage(null) }}><aside className="passage-drawer" onMouseDown={event => event.stopPropagation()}><div className="drawer-head"><div><span className="eyebrow">SOURCE PASSAGE</span><h2>{passage.filename || passage.document_id}</h2></div><button className="icon-button" onClick={() => { activePassageId.current = null; setPassage(null) }} aria-label="Close"><X size={20} /></button></div><div className="passage-meta">Page {passage.page} · {passage.id}</div><div className="passage-language-actions"><button className="view-toggle" disabled={translatingPassage} onClick={() => showPassageTranslation ? setShowPassageTranslation(false) : void showHindiPassage()}><Languages size={14} />{translatingPassage ? 'Preparing Hindi…' : showPassageTranslation ? 'Hide Hindi' : 'Read in Hindi'}</button></div>{translationError && <div className="translation-inline-error">{translationError}</div>}{showPassageTranslation && <div className="translated-source"><small>हिंदी · MACHINE TRANSLATION</small><p>{passageTranslation}</p></div>}<span className="eyebrow">ORIGINAL ENGLISH EVIDENCE</span><div className="source-text">{passage.text}</div><a className="primary-button drawer-link" href={`/api/documents/${passage.document_id}/file#page=${passage.page}`} target="_blank" rel="noreferrer">Open original document, page {passage.page}</a></aside></div>}
  </div>
}
