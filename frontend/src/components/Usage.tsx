import { useState, useEffect } from 'react'
import { useAuthFetch, fmtUSD, fmtTime, txLink } from '../lib'

interface UsageRecord {
  id: number
  model: string
  input_tokens: number
  output_tokens: number
  cost_cents: number
  tx_hash: string
  created_at: number
}

export function Usage() {
  const authFetch = useAuthFetch()
  const [records, setRecords] = useState<UsageRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const limit = 50

  const load = async (newOffset: number) => {
    try {
      const res = await authFetch(`/api/user/usage?limit=${limit}&offset=${newOffset}`)
      if (res.ok) {
        const data = await res.json()
        const newRecords = data.usage || []
        setRecords(prev => newOffset === 0 ? newRecords : [...prev, ...newRecords])
        setHasMore(newRecords.length === limit)
      }
    } catch (e) {
      console.error('usage fetch failed', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0) }, [])

  const totalSpend = records.reduce((sum, r) => sum + r.cost_cents, 0)

  return (
    <div>
      <h1>Usage History</h1>
      <p className="sub">lifetime saved — every request, model, and transaction</p>

      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <p className="dim" style={{ fontSize: 11 }}>Total shown: {records.length} calls</p>
          <p style={{ fontSize: 20, color: '#00ff9c', fontWeight: 'bold' }}>{fmtUSD(totalSpend)}</p>
        </div>
        <span className="dim" style={{ fontSize: 11 }}>page {Math.floor(offset / limit) + 1}</span>
      </div>

      {loading ? (
        <div className="card"><h2>Loading...</h2></div>
      ) : records.length === 0 ? (
        <div className="card">
          <p className="dim">No usage records yet. Your requests will appear here permanently.</p>
        </div>
      ) : (
        <div style={{ marginTop: 16 }}>
          {/* Table */}
          <div className="card" style={{ padding: 0, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #2a2a2a' }}>
                  <th style={thStyle}>Date/Time</th>
                  <th style={thStyle}>Model</th>
                  <th style={thStyle}>Tokens (in/out)</th>
                  <th style={thStyle}>Amount</th>
                  <th style={thStyle}>Tx (Basescan)</th>
                </tr>
              </thead>
              <tbody>
                {records.map(r => {
                  const link = txLink(r.tx_hash)
                  return (
                    <tr key={r.id} style={{ borderBottom: '1px solid #1a1a1a' }}>
                      <td style={tdStyle} className="dim">{fmtTime(r.created_at)}</td>
                      <td style={tdStyle} className="dim" style={{ color: '#5ce1ff' }}>{r.model}</td>
                      <td style={tdStyle} className="dim">{r.input_tokens}/{r.output_tokens}</td>
                      <td style={tdStyle} style={{ color: '#00ff9c', fontWeight: 'bold' }}>{fmtUSD(r.cost_cents)}</td>
                      <td style={tdStyle} className="dim">
                        {link ? <a href={link.url} target="_blank" rel="noopener">{link.short}</a> : '—'}
                      </td>
                    </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>

          {hasMore && (
            <button
              className="btn btn-outline"
              style={{ marginTop: 16, width: '100%' }}
              onClick={() => { const next = offset + limit; setOffset(next); load(next) }}
            >
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  )
}

const thStyle = {
  padding: '8px 12px', textAlign: 'left' as const, fontWeight: 'bold' as const,
  color: '#888', fontSize: 11,
}
const tdStyle = {
  padding: '8px 12px',
}
