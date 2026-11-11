import { useEffect, useState } from 'react';
import { Upload, RefreshCw, FileText, CheckCircle2, AlertTriangle, XCircle, Eye } from 'lucide-react';

const api = 'http://localhost:8000/api';
type Invoice = { id: number; filename: string; decision: string; method: string; data: any; result: any; human_decision?: string };

async function request(path: string, init?: RequestInit) {
  const response = await fetch(api + path, init);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export default function App() {
  const [items, setItems] = useState<Invoice[]>([]);
  const [summary, setSummary] = useState<any>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Invoice | null>(null);

  async function refresh() {
    try {
      const [invoiceData, dashboard] = await Promise.all([request('/invoices'), request('/dashboard/summary')]);
      setItems(invoiceData.items);
      setSummary(dashboard);
      setError('');
    } catch (e: any) { setError(e.message); }
  }
  useEffect(() => { refresh(); }, []);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    const form = new FormData();
    Array.from(files).forEach(file => form.append('files', file));
    try { await request('/invoices/upload', { method: 'POST', body: form }); await refresh(); }
    catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function reprocess(id: number) {
    setBusy(true);
    try {
      const updated = await request(`/invoices/${id}/process`, { method: 'POST' });
      setSelected(updated);
      await refresh();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  return <main>
    <header><div className="brand"><div className="mark">Z</div><div><h1>Invoice Reconciliation</h1><p>Accounts payable operations</p></div></div><button className="subtle" onClick={refresh}><RefreshCw size={16}/> Refresh</button></header>
    <section className="metrics">{[['Processed', summary.total, FileText], ['Approved', summary.approved, CheckCircle2], ['Needs review', summary.review, AlertTriangle], ['Rejected', summary.rejected, XCircle]].map(([label, value, Icon]: any) => <article className="metric" key={label}><Icon size={19}/><span>{label}</span><b>{value || 0}</b></article>)}</section>
    <section className="upload"><div><h2>Process invoices</h2><p>Upload PDFs for extraction and reconciliation.</p></div><label className="uploadbtn"><Upload size={17}/>{busy ? 'Processing…' : 'Choose PDF invoices'}<input type="file" accept="application/pdf,.pdf" multiple disabled={busy} onChange={e => upload(e.target.files)}/></label></section>
    {error && <div className="error">{error}</div>}
    <section className="panel"><div className="panelhead"><div><h2>Processing history</h2><p>Persisted in local SQLite</p></div><span>{items.length} invoices</span></div><div className="tablewrap"><table><thead><tr><th>File</th><th>Invoice #</th><th>Vendor</th><th>Total</th><th>Extraction</th><th>Decision</th><th/></tr></thead><tbody>{items.map(invoice => <tr key={invoice.id}><td><FileText size={16}/>{invoice.filename}</td><td>{invoice.data?.invoice_number || '—'}</td><td>{invoice.data?.vendor_name || '—'}</td><td>{invoice.data?.total_amount == null ? '—' : `${invoice.data.currency || ''} ${Number(invoice.data.total_amount).toLocaleString()}`}</td><td>{invoice.method}</td><td><span className={'badge ' + invoice.decision.toLowerCase()}>{invoice.decision.replace('_', ' ')}</span></td><td><button className="icon" onClick={() => setSelected(invoice)} title="View details"><Eye size={17}/></button></td></tr>)}</tbody></table>{!items.length && <div className="empty">No invoices yet. Upload PDFs to start.</div>}</div></section>
    {selected && <div className="shade" onClick={() => setSelected(null)}><section className="modal" onClick={e => e.stopPropagation()}><button className="close" onClick={() => setSelected(null)}>×</button><h2>{selected.filename}</h2><p className="decision">{selected.decision.replace('_', ' ')}</p><h3>Decision explanation</h3><ul>{(selected.result?.reasons || []).map((reason: string, index: number) => <li key={index}>{reason}</li>)}</ul><h3>Validation checks</h3><div className="checks">{(selected.result?.checks || []).map((check: any) => <div key={check.name}><b>{check.passed ? '✓' : '!'} {check.name.replaceAll('_', ' ')}</b><span>{check.detail}</span></div>)}</div><p><b>Recommended action:</b> {selected.result?.recommended_action}</p><button className="subtle" disabled={busy} onClick={() => reprocess(selected.id)}>{busy ? 'Reprocessing…' : 'Reprocess with current rules'}</button>{selected.decision === 'NEEDS_REVIEW' && <Review id={selected.id} done={async () => { setSelected(null); await refresh(); }}/>}</section></div>}
  </main>;
}

function Review({ id, done }: { id: number; done: () => void }) {
  const [action, setAction] = useState('APPROVED');
  const [reason, setReason] = useState('Verified by human reviewer');
  const [error, setError] = useState('');
  async function save() {
    try { await request(`/invoices/${id}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewer: 'Local reviewer', action, reason, notes: '' }) }); done(); }
    catch (e: any) { setError(e.message); }
  }
  return <div className="review"><h3>Record human review</h3><select value={action} onChange={e => setAction(e.target.value)}><option>APPROVED</option><option>REJECTED</option></select><input value={reason} onChange={e => setReason(e.target.value)}/><button onClick={save}>Save human decision</button>{error && <p>{error}</p>}</div>;
}
