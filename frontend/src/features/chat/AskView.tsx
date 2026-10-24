import { useMemo, useRef, useState } from 'react'
import { ReactFlow, Background, Controls, MarkerType, type Node, type Edge } from '@xyflow/react'
import { ArrowRight, BookOpen, Languages, MessageSquareText, Send, Sparkles } from 'lucide-react'
import { api, json, type Answer, type Conflict, type Translation } from '../../api/client'
import './ask-conflicts.css'

type Props = { openPassage: (id: string) => void }
const examples = [
  'What are the main themes across these reports?',
  'Which dataset did the project using YOLOv8 evaluate on?',
  'Explain the approach to road damage detection.',
  'RoadWatch कौन सी विधि उपयोग करता है?',
]

export default function AskView({ openPassage }: Props) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hindiReading, setHindiReading] = useState('')
  const [showHindiReading, setShowHindiReading] = useState(false)
  const [translationBusy, setTranslationBusy] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const requestVersion = useRef(0)

  async function submit(value = question) {
    if (!value.trim()) return
    const version = ++requestVersion.current
    setLoading(true); setError(''); setQuestion(value); setHindiReading(''); setShowHindiReading(false); setTranslationBusy(false); setTranslationError('')
    try { const result = await api<Answer>('/ask', json('POST', { question: value })); if (version === requestVersion.current) setAnswer(result) }
    catch (cause) { if (version === requestVersion.current) setError((cause as Error).message) }
    finally { if (version === requestVersion.current) setLoading(false) }
  }

  async function translateAnswer() {
    if (!answer) return
    if (hindiReading) { setShowHindiReading(true); return }
    const version = requestVersion.current
    setTranslationBusy(true); setTranslationError('')
    try {
      const source = answer.language === 'hi' && answer.sources[0] ? answer.sources[0].text : answer.answer
      const translated = await api<Translation>('/translate/text', json('POST', { text: source.slice(0, 5000) }))
      if (version === requestVersion.current) { setHindiReading(translated.translated_text); setShowHindiReading(true) }
    } catch (cause) { if (version === requestVersion.current) setTranslationError((cause as Error).message) }
    finally { if (version === requestVersion.current) setTranslationBusy(false) }
  }

  const path = useMemo(() => {
    const nodes: Node[] = (answer?.graph_path?.nodes || []).map((item, index) => ({ id: item.id,
      position: { x: 60 + index * 205, y: 95 }, data: { label: <div className="flow-node"><small>{item.type}</small><strong>{item.name}</strong></div> },
      style: { background: '#192742', color: '#f4f8ff', border: '2px solid #72dcba', borderRadius: 12, minWidth: 145 } }))
    const edges: Edge[] = (answer?.graph_path?.edges || []).map(item => ({ id: item.id, source: item.source, target: item.target,
      label: `${item.polarity === 'denies' ? 'denies ' : ''}${item.relation.replaceAll('_', ' ').toLowerCase()}`, animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, color: item.polarity === 'denies' ? '#e9a09c' : '#72dcba' },
      style: { stroke: item.polarity === 'denies' ? '#e9a09c' : '#72dcba', strokeWidth: 2.5 },
      labelStyle: { fill: '#d0f4e9', fontSize: 11 }, labelBgStyle: { fill: '#101a2d' } }))
    return { nodes, edges }
  }, [answer])

  return <div className="page-content ask-page"><div className="page-heading"><div><span className="eyebrow">ASK THE COLLECTION</span><h1>Ask NexusMind</h1><p>Answers are built from reviewed graph facts and passages in your uploaded reports. Hindi questions are supported.</p></div></div>
    <div className="ask-layout"><section className="panel ask-panel"><div className="ask-intro"><span className="ask-symbol"><Sparkles size={25} /></span><h2>Find the connection</h2><p>Ask about shared themes, a project’s methods, its datasets, or an approach described in the reports.</p></div><div className="examples">{examples.map(example => <button key={example} onClick={() => { void submit(example) }}>{example}<ArrowRight size={14} /></button>)}</div><form className="ask-form" onSubmit={event => { event.preventDefault(); void submit() }}><textarea rows={3} value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask a question about your reports…" /><button className="primary-button" disabled={loading || !question.trim()}><Send size={15} />{loading ? 'Searching…' : 'Ask question'}</button></form>{error && <div className="notice error">{error}</div>}</section>
      <section className="panel answer-panel"><div className="panel-heading"><h2>Answer</h2>{answer && <div className="answer-heading-actions"><button className="view-toggle" disabled={translationBusy} onClick={() => showHindiReading ? setShowHindiReading(false) : void translateAnswer()}><Languages size={14} />{translationBusy ? 'Translating…' : showHindiReading ? 'Hide Hindi' : 'Read in Hindi'}</button><span className="route-pill">{answer.route}</span></div>}</div>{!answer ? <div className="empty-state"><MessageSquareText size={34} /><h3>Ask your first question</h3><p>The supporting sources and graph path will appear here.</p></div> : <div className="answer-content">{answer.graph_unavailable && <div className="notice">Graph service is unavailable. Showing passage evidence only; no graph path is claimed.</div>}{translationError && <div className="translation-inline-error">{translationError}</div>}{showHindiReading && <div className="translated-source"><small>हिंदी · MACHINE TRANSLATION</small><p>{hindiReading}</p></div>}<div className={'answer-statement ' + (answer.insufficient_evidence ? 'uncertain' : '')}>{answer.answer}</div><ConflictsView conflicts={answer.conflicts || []} openPassage={openPassage} />{answer.topics && <div className="answer-topics">{answer.topics.map(topic => <div key={topic.id} className="topic-summary"><strong>{topic.label}</strong><small>{topic.documents.map(doc => doc.filename).join(', ')}</small></div>)}</div>}{path.nodes.length > 0 && <div className="answer-path"><div className="section-caption"><GitPathIcon /> Evidence path</div><div className="path-canvas"><ReactFlow nodes={path.nodes} edges={path.edges} fitView proOptions={{ hideAttribution: true }} onEdgeClick={(_, edge) => { const original = answer.graph_path.edges.find(item => item.id === edge.id); if (original) openPassage(original.evidence_chunk_id) }}><Background color="#26354e" gap={22} /><Controls /></ReactFlow></div><p className="hint">Click a connection to open its supporting passage.</p></div>}{answer.sources.length > 0 && <div className="answer-sources"><div className="section-caption"><BookOpen size={15} /> Supporting passages</div>{answer.sources.map((source, index) => <button key={source.chunk_id + index} className="source-card" onClick={() => openPassage(source.chunk_id)}><span className="source-index">{index + 1}</span><span><strong>{source.filename} · page {source.page}</strong><small>{source.text.slice(0, 170)}{source.text.length > 170 ? '…' : ''}</small></span><ArrowRight size={15} /></button>)}</div>}</div>}</section></div>
  </div>
}

function GitPathIcon() { return <span className="path-line-icon">●—●</span> }

function ConflictsView({ conflicts, openPassage }: { conflicts: Conflict[]; openPassage: (id: string) => void }) {
  if (!conflicts.length) return null
  return <section className="conflict-section"><div className="section-caption">Conflicting source claims</div>
    {conflicts.map(conflict => <div className="conflict-pair" key={conflict.id}>
      <strong>{conflict.subject} · {conflict.relation.replaceAll('_', ' ').toLowerCase()} · {conflict.object}</strong>
      <div className="claim-grid">{conflict.claims.map(claim => <button key={claim.id} className={'claim-card ' + claim.polarity} onClick={() => openPassage(claim.evidence_chunk_id)}>
        <span>{claim.polarity === 'denies' ? 'DENIES' : 'SUPPORTS'}</span><small>{claim.filename} · page {claim.page}</small><p>“{claim.evidence_quote}”</p>
      </button>)}</div>
    </div>)}
  </section>
}
