import { useState, useEffect } from 'react'
import { useAuthFetch, fmtUSD, fmtTime, shortAddr, txLink } from '../lib'

interface UsageRecord {
  id: number
  model: string
  input_tokens: number
  output_tokens: number
  cost_cents: number
  tx_hash: string
  created_at: number
}

export function Activity() {
  const authFetch = useAuthFetch()
  const [records, setRecords] = useState<UsageRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)

  useEffect(() => {
    let interval: any
    const load = async () => {
      try {
        const res = await authFetch('/api/user/activity')
        if (res.ok) {
          const data = await res.json()
          setRecords(data.activity || [])
        }
      } catch (e) {
        console.error('activity fetch failed', e)
      } finally {
        setLoading(false)
      }
    }
    if (autoRefresh) {
      load()
      interval = setInterval(load, 5000) // instant updates — poll every 5s
    }
    return () => { if (interval) clearInterval(interval) }
  }, [autoRefresh])

  return (
    <div>
      <h1>Activity</h1>
      <p className="sub">live updates of every API call and its cost</p>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span className="dim">
          {records.length > 0 ? `${records.length} recent calls` : 'no calls yet'}
        </span>
        <button
          className={autoRefresh ? 'btn' : 'btn btn-outline'}
          style={{ fontSize: 12, padding: '4px 12px' }}
          onClick={() => setAutoRefresh(!autoRefresh)}
        >
          {autoRefresh ? '● live' : 'paused'}
        </button>
      </div>

      {loading ? (
        <div className="card"><h2>Loading...</h2></div>
      ) : records.length === 0 ? (
        <div className="card">
          <p className="dim">No activity yet. Make your first API request to see it here instantly.</p>
        </div>
      ) : (
        <div>
          {records.map((r, i) => (
            <div className="card" key={r.id} style={{
              marginBottom: 8,
              padding: 12,
              borderLeft: i === 0 ? '3px solid #00ff9c' : '1px solid #1a1a1a',
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <div>
                    <span style={{ color: '#5ce1ff', fontSize: 13, fontWeight: 'bold' }}>
                      {r.model}
                    </span>
                    <span className="dim" style={{ marginLeft: 8, fontSize: 11 }}>
                      {i === 0 && '● new · '}
                      {fmtTime(r.created_at)}
                    </span>
                  </div>
                  <span style={{ color: '#00ff9c', fontWeight: 'bold', fontSize: 13 }}>
                    {fmtUSD(r.cost_cents)}
                  </span>
                </div>
                <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
                  {r.input_tokens} in · {r.output_tokens} out
                  {r.tx_hash && (() => {
                    const link = txLink(r.tx_hash)
                    return link ? <> · tx: <a href={link.url} target="_blank" rel="noopener">{link.short}</a></> : null
                  })()}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
