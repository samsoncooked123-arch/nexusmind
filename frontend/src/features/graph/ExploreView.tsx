import { useEffect, useMemo, useRef, useState } from 'react'
import { ReactFlow, Background, Controls, MarkerType, Position, type Edge, type Node } from '@xyflow/react'
import { Compass, GitBranch, Plus, RefreshCw, RotateCcw } from 'lucide-react'
import { api, json, type Document, type GraphData, type GraphNode, type Topic } from '../../api/client'

type Props = { documents: Document[]; openPassage: (id: string) => void }
const colors: Record<string, string> = { Project: '#4f8df7', Method: '#ab84ff', Dataset: '#eeb96b', Organization: '#67c6ab' }

export default function ExploreView({ documents, openPassage }: Props) {
  const [topics, setTopics] = useState<Topic[]>([])
  const [entities, setEntities] = useState<GraphNode[]>([])
  const [graph, setGraph] = useState<GraphData>({ nodes: [], edges: [] })
  const [graphLoading, setGraphLoading] = useState(false)
  const [selectedEntity, setSelectedEntity] = useState('')
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const topicInputRef = useRef<HTMLInputElement>(null)
  const graphRequest = useRef(0)
  const [label, setLabel] = useState('')
  const [members, setMembers] = useState<string[]>([])
  const [mergeId, setMergeId] = useState('')
  const [splitLabel, setSplitLabel] = useState('')
  const [splitMembers, setSplitMembers] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function reload() {
    setTopics(await api<Topic[]>('/topics'))
    try { setEntities(await api<GraphNode[]>('/graph/entities?limit=30')) }
    catch { setEntities([]) }
  }
  useEffect(() => { void reload().catch(cause => setError(cause.message)) }, [])
  useEffect(() => { void loadGraph('/graph/overview') }, [])
  useEffect(() => { if (editorOpen && !selectedTopic) topicInputRef.current?.focus() }, [editorOpen, selectedTopic])
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void api<GraphNode[]>(`/graph/entities?query=${encodeURIComponent(search)}&limit=30`).then(setEntities).catch(() => setEntities([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search])

  async function loadGraph(path: string) {
    const request = ++graphRequest.current
    setGraphLoading(true)
    try {
      const result = await api<GraphData>(path)
      if (request === graphRequest.current) setGraph(result)
    } catch (cause) {
      if (request === graphRequest.current) setError((cause as Error).message)
    } finally {
      if (request === graphRequest.current) setGraphLoading(false)
    }
  }
  function showOverview() {
    setSelectedEntity(''); setSelectedTopic(null); setEditorOpen(false); setError('')
    void loadGraph('/graph/overview')
  }
  function selectEntity(id: string) {
    setSelectedEntity(id); setSelectedTopic(null); setEditorOpen(false); setError('')
    void loadGraph(`/graph/neighborhood/${encodeURIComponent(id)}`)
  }
  function selectTopic(topic: Topic) {
    setSelectedTopic(topic); setLabel(topic.label); setMembers(topic.documents.map(doc => doc.id)); setSplitMembers([]); setSplitLabel(''); setMergeId(''); setSelectedEntity(''); setEditorOpen(false)
    setError(''); void loadGraph(`/graph/topic/${topic.id}`)
  }
  async function saveTopic() {
    setBusy(true); setError('')
    try {
      const body = { label, document_ids: members, status: 'approved' }
      await api(selectedTopic ? `/topics/${selectedTopic.id}` : '/topics', json(selectedTopic ? 'PATCH' : 'POST', body))
      await reload(); setLabel(''); setMembers([]); showOverview()
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }
  async function discover() {
    setBusy(true); setError('')
    try { await api('/topics/discover', { method: 'POST' }); await reload() }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }
  async function merge() {
    if (!selectedTopic || !mergeId) return
    setBusy(true); setError('')
    try { await api(`/topics/${selectedTopic.id}/merge`, json('POST', { secondary_id: mergeId })); await reload(); setMergeId(''); showOverview() }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }
  async function split() {
    if (!selectedTopic || !splitLabel || !splitMembers.length) return
    setBusy(true); setError('')
    try { await api(`/topics/${selectedTopic.id}/split`, json('POST', { label: splitLabel, document_ids: splitMembers })); await reload(); setSplitMembers([]); setSplitLabel(''); showOverview() }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  const filtered = entities
  const showingMap = !selectedEntity
  const repeatedNames = new Set(filtered.map(entity => entity.name).filter(name => filtered.filter(item => item.name === name).length > 1))
  const overviewGroups = useMemo(() => {
    const byId = new Map(graph.nodes.map(node => [node.id, node]))
    return graph.nodes.filter(node => node.type === 'Project').map(project => ({
      project,
      connections: graph.edges.filter(edge => edge.source === project.id).map(edge => ({
        edge, target: byId.get(edge.target),
      })).filter(item => item.target),
    })).filter(group => group.connections.length)
  }, [graph])
  const flow = useMemo(() => {
    const visibleEdges = graph.edges.slice(0, 24)
    const used = new Set(visibleEdges.flatMap(edge => [edge.source, edge.target]))
    if (selectedEntity) used.add(selectedEntity)
    const ordered = graph.nodes.filter(node => used.has(node.id))
    const projects = ordered.filter(node => node.type === 'Project')
    const related = ordered.filter(node => node.type !== 'Project')
    const rowGap = 112
    const height = Math.max(projects.length, related.length) * rowGap
    const positions = new Map<string, { x: number; y: number }>()
    for (const [column, items] of [[0, projects], [1, related]] as const) {
      const offset = (height - items.length * rowGap) / 2
      items.forEach((item, index) => positions.set(item.id, { x: 24 + column * 250, y: 30 + offset + index * rowGap }))
    }
    const nodes: Node[] = ordered.map(item => {
      return { id: item.id, position: positions.get(item.id) || { x: 24, y: 30 },
        sourcePosition: Position.Right, targetPosition: Position.Left,
        data: { label: <div className="flow-node" title={item.topics?.length ? `${item.name} · ${item.topics.join(' / ')}` : item.name}><small>{item.type}</small><strong>{item.name}</strong></div> },
        style: { background: 'linear-gradient(145deg,#213550,#13263d)', color: '#eef4ff',
          border: `1.5px solid ${colors[item.type] || '#8d9db8'}`, borderRadius: 12, width: 160, minHeight: 67,
          boxShadow: '0 15px 0 -9px #071523,0 20px 28px #06102188' } }
    })
    const edges: Edge[] = visibleEdges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, type: 'default',
      label: `${edge.polarity === 'denies' ? 'denies ' : ''}${edge.relation.replaceAll('_', ' ').toLowerCase()}`,
      markerEnd: { type: MarkerType.ArrowClosed, color: edge.polarity === 'denies' ? '#e7a3a4' : '#8296b5' },
      style: { stroke: edge.polarity === 'denies' ? '#e7a3a4' : '#8296b5', strokeWidth: 2 }, labelStyle: { fill: '#e0eafb', fontSize: 11, fontWeight: 700 },
      labelBgPadding: [8, 5], labelBgBorderRadius: 6,
      labelBgStyle: { fill: '#101a2d', fillOpacity: 1, stroke: '#344b68', strokeWidth: 1 } }))
    return { nodes, edges }
  }, [graph, selectedEntity])

  return <div className="page-content"><div className="page-heading"><div><span className="eyebrow">EXPLORE CONNECTIONS</span><h1>Topics & graph</h1><p>Review topic groups, browse entities, and open the passage behind any relationship.</p></div><button className="secondary-button" onClick={() => { void discover() }} disabled={busy}><RefreshCw size={16} /> Suggest topics</button></div>
    {error && <div className="notice error">{error}</div>}
    <div className="explore-grid"><section className="panel topic-panel"><div className="panel-heading"><h2>Topic groups</h2><button className="icon-button" title="Create topic" aria-label="Create topic" aria-expanded={editorOpen && !selectedTopic} onClick={() => { setSelectedTopic(null); setLabel(''); setMembers([]); setEditorOpen(true) }}><Plus size={18} /></button></div>{topics.length ? <div className="topic-list">{topics.map(topic => <button key={topic.id} className={'topic-row ' + (selectedTopic?.id === topic.id ? 'selected' : '')} onClick={() => selectTopic(topic)}><span className="topic-icon"><Compass size={17} /></span><span><strong>{topic.label}</strong><small>{topic.documents.length} documents · {topic.status}</small></span></button>)}</div> : <div className="empty-state small"><Compass size={28} /><p>No topics yet. Suggest them from reports or create one below.</p></div>}<details className="topic-editor" key={selectedTopic?.id || 'new'} open={editorOpen} onToggle={event => setEditorOpen(event.currentTarget.open)}><summary>{selectedTopic ? 'Edit topic membership' : 'Create a topic'}</summary><span className="eyebrow">{selectedTopic ? 'EDIT TOPIC' : 'NEW TOPIC'}</span><input ref={topicInputRef} value={label} onChange={event => setLabel(event.target.value)} placeholder="Topic name" /><div className="member-list">{documents.filter(doc => doc.status === 'ready').map(doc => <label key={doc.id}><input type="checkbox" checked={members.includes(doc.id)} onChange={event => setMembers(event.target.checked ? [...members, doc.id] : members.filter(id => id !== doc.id))} /><span>{doc.filename}</span></label>)}</div><button className="primary-button" disabled={!label || !members.length || busy} onClick={() => { void saveTopic() }}>{selectedTopic?.status === 'suggested' ? 'Approve topic' : 'Save topic'}</button>{selectedTopic && <div className="topic-tools"><span className="eyebrow">MERGE INTO THIS TOPIC</span><select value={mergeId} onChange={event => setMergeId(event.target.value)}><option value="">Choose another topic</option>{topics.filter(topic => topic.id !== selectedTopic.id).map(topic => <option key={topic.id} value={topic.id}>{topic.label}</option>)}</select><button className="secondary-button" disabled={!mergeId || busy} onClick={() => { void merge() }}>Merge topics</button><span className="eyebrow">SPLIT THIS TOPIC</span><input value={splitLabel} onChange={event => setSplitLabel(event.target.value)} placeholder="New topic name" /><div className="member-list">{selectedTopic.documents.map(doc => <label key={doc.id}><input type="checkbox" checked={splitMembers.includes(doc.id)} onChange={event => setSplitMembers(event.target.checked ? [...splitMembers, doc.id] : splitMembers.filter(id => id !== doc.id))} /><span>{doc.filename}</span></label>)}</div><button className="secondary-button" disabled={!splitLabel || !splitMembers.length || splitMembers.length >= selectedTopic.documents.length || busy} onClick={() => { void split() }}>Move selected into new topic</button></div>}</details></section>
    <section className="panel graph-panel">
      <div className="panel-heading"><div><h2>Knowledge graph</h2><p>{selectedEntity ? 'Entity connections' : selectedTopic ? `${selectedTopic.label} connections` : 'Up to 24 reviewed connections across documents'}</p></div><div className="graph-heading-actions"><button className="view-toggle" onClick={showOverview} aria-label="Show relationship overview"><RotateCcw size={14} /> Overview</button><span className="count-badge">{showingMap ? graph.nodes.length : flow.nodes.length} nodes</span></div></div>
      <div className="entity-search"><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Find an entity…" /></div>
      <div className="entity-chips">{filtered.slice(0, 30).map(entity => <button key={entity.id} className={'entity-chip ' + (selectedEntity === entity.id ? 'active' : '')} onClick={() => { selectEntity(entity.id) }}>{entity.name}{repeatedNames.has(entity.name) && <small> · {entity.topics?.join(' / ') || entity.id.slice(-4)}</small>}</button>)}</div>
      <div className={'graph-canvas ' + (showingMap ? 'overview' : '')}>
        {graphLoading ? <div className="empty-state"><GitBranch size={30} /><p>Loading reviewed connections…</p></div>
          : graph.nodes.length && showingMap ? <div className="overview-list">{overviewGroups.map(({ project, connections }) => <section className="overview-project" key={project.id}>
            <button className="overview-project-title" onClick={() => selectEntity(project.id)}><span><small>PROJECT{project.topics?.length ? ` · ${project.topics.join(' / ')}` : ''}</small><strong>{project.name}</strong></span><span aria-hidden="true">↗</span></button>
            <div className="overview-relations">{connections.map(({ edge, target }) => <button key={edge.id} className="overview-relation" onClick={() => openPassage(edge.evidence_chunk_id)}>
              <span className="overview-relation-name">{edge.relation.replaceAll('_', ' ').toLowerCase()} <span aria-hidden="true">→</span></span><strong>{target?.name}</strong><small>{edge.evidence?.filename || 'Source passage'}{edge.evidence?.page ? ` · page ${edge.evidence.page}` : ''}</small>
            </button>)}</div>
          </section>)}</div>
          : graph.nodes.length ? <ReactFlow key={selectedEntity || selectedTopic?.id || 'graph'} nodes={flow.nodes} edges={flow.edges} fitView fitViewOptions={{ padding: 0.06, maxZoom: 1.35 }} proOptions={{ hideAttribution: true }} onNodeClick={(_, node) => { selectEntity(node.id) }} onEdgeClick={(_, edge) => { const original = graph.edges.find(item => item.id === edge.id); if (original) openPassage(original.evidence_chunk_id) }}><Background color="#24334d" gap={24} /><Controls /></ReactFlow>
          : <div className="empty-state"><GitBranch size={34} /><h3>No reviewed connections yet</h3><p>Approve facts to build the graph, or select an entity to inspect it.</p></div>}
      </div>
    </section></div>
  </div>
}
