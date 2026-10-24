import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ChevronLeft, ChevronRight, FileText, Layers3, ScanText } from 'lucide-react'
import type { Chunk, Document } from '../../api/client'
import './document-map.css'

type Props = { document: Document; page: number; chunks: Chunk[]; openPassage: (id: string) => void;
  language: 'en' | 'hi'; translations: Record<string, string> }

function Connector({ label }: { label: string }) {
  return <div className="flow-connector" aria-label={label} role="img">
    <span className="flow-connector-line" />
    <ArrowDown size={22} strokeWidth={3} aria-hidden="true" />
    <span className="flow-connector-label">{label}</span>
  </div>
}

export default function DocumentMap({ document, page, chunks, openPassage, language, translations }: Props) {
  const [passageIndex, setPassageIndex] = useState(0)
  useEffect(() => setPassageIndex(0), [document.id, document.version, page])
  const onPage = useMemo(() => chunks.filter(chunk => chunk.page === page), [chunks, page])
  const passage = onPage[passageIndex]
  const shown = passage ? language === 'hi' ? translations[passage.id] || 'Translating passage…' : passage.text : ''

  return <div className="document-map-shell"><div className="map-navigation"><span><strong>Document flow</strong><small>Source → page → passage</small></span>
    {onPage.length > 1 && <div><button onClick={() => setPassageIndex(index => Math.max(0, index - 1))} disabled={passageIndex === 0} aria-label="Previous passage"><ChevronLeft size={16} /></button><span>{passageIndex + 1} / {onPage.length}</span><button onClick={() => setPassageIndex(index => Math.min(onPage.length - 1, index + 1))} disabled={passageIndex >= onPage.length - 1} aria-label="Next passage"><ChevronRight size={16} /></button></div>}
  </div><div className="document-map" aria-label="Document to page to passage flowchart">
      <div className="flow-card flow-document"><FileText size={20} aria-hidden="true" /><small>SOURCE DOCUMENT</small><strong>{document.filename}</strong><span>Version {document.version} · {document.page_count} {document.page_count === 1 ? 'page' : 'pages'}</span></div>
      <Connector label="contains" />
      <div className="flow-card flow-page"><Layers3 size={20} aria-hidden="true" /><small>EXTRACTED PAGE</small><strong>Page {page}</strong><span>{onPage.length} {onPage.length === 1 ? 'passage' : 'passages'} on this page</span></div>
      <Connector label="yields" />
      {passage ? <button className="flow-card flow-passage" onClick={() => openPassage(passage.id)}><ScanText size={19} aria-hidden="true" /><small>EVIDENCE PASSAGE {passageIndex + 1} OF {onPage.length}</small><strong>{shown.slice(0, 145)}{shown.length > 145 ? '…' : ''}</strong><span>Open original evidence ↗</span></button> : <div className="flow-card flow-empty"><ScanText size={19} aria-hidden="true" /><small>EVIDENCE PASSAGE</small><strong>No extracted text on this page</strong></div>}
    </div></div>
}
