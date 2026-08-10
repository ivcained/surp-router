import { useState, useEffect } from 'react'
import { useAuthFetch, fmtUSD, fmtTime } from '../lib'

interface ApiKey {
  key_id: string
  name: string
  budget_cents: number
  spent_cents: number
  created_at: number
}

interface CreateResult {
  key: string
  key_id: string
  name: string
  budget_cents: number
  warning: string
}

export function ApiKeys() {
  const authFetch = useAuthFetch()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newBudget, setNewBudget] = useState('')  // dollars
  const [createdKey, setCreatedKey] = useState<CreateResult | null>(null)
  const [copied, setCopied] = useState(false)

  const loadKeys = async () => {
    try {
      const res = await authFetch('/api/user/api-keys')
      if (res.ok) {
        const data = await res.json()
        setKeys(data.api_keys || [])
      }
    } catch (e) {
      console.error('load keys failed', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadKeys() }, [])

  const handleCreate = async () => {
    try {
      const budgetCents = Math.round((parseFloat(newBudget) || 0) * 100)
      const res = await authFetch('/api/user/api-keys', {
        method: 'POST',
        body: JSON.stringify({ name: newName, budget_cents: budgetCents }),
      })
      const data = await res.json()
      if (res.ok) {
        setCreatedKey(data)
        setNewName('')
        setNewBudget('')
        setShowCreate(false)
        loadKeys()
      }
    } catch (e) {
      console.error('create key failed', e)
    }
  }

  const handleDelete = async (keyId: string) => {
    if (!confirm('Revoke this API key? This cannot be undone.')) return
    try {
      const res = await authFetch(`/api/user/api-keys/${keyId}`, { method: 'DELETE' })
      if (res.ok) loadKeys()
    } catch (e) {
      console.error('delete key failed', e)
    }
  }

  const copyKey = () => {
    if (createdKey) {
      navigator.clipboard.writeText(createdKey.key)
      setCopied(true)
    }
  }

  if (loading) return <div className="card"><h2>Loading...</h2></div>

  return (
    <div>
      <h1>API Keys</h1>
      <p className="sub">create keys with per-key spend budgets</p>

      {/* Created key modal — shown only once */}
      {createdKey && (
        <div className="card" style={{ border: '2px solid #00ff9c', marginBottom: 16 }}>
          <h2 style={{ color: '#00ff9c' }}>⚠ Your New API Key</h2>
          <p style={{ color: '#ffd23f', fontWeight: 'bold', marginBottom: 12 }}>
            {createdKey.warning}
          </p>
          <div className="wallet-addr" style={{ fontSize: 11, wordBreak: 'break-all' }}>
            {createdKey.key}
          </div>
          <button className="btn" onClick={copyKey}>
            {copied ? '✓ copied' : 'copy key'}
          </button>
          <button
            className="btn btn-outline"
            style={{ marginLeft: 8 }}
            onClick={() => { setCreatedKey(null); setCopied(false) }}
          >
            I've saved it — close
          </button>
        </div>
      )}

      {/* Create new key */}
      {showCreate ? (
        <div className="card">
          <h2>Create New API Key</h2>
          <label className="dim" style={{ display: 'block', marginBottom: 4 }}>Name</label>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="production app"
            style={inputStyle}
          />
          <label className="dim" style={{ display: 'block', marginBottom: 4, marginTop: 12 }}>
            Spend budget (USD) — 0 for unlimited
          </label>
          <input
            type="text"
            value={newBudget}
            onChange={(e) => setNewBudget(e.target.value)}
            placeholder="10.00"
            style={inputStyle}
          />
          <p className="dim" style={{ fontSize: 11, marginTop: 4 }}>
            The key will stop working once it reaches this budget. Set 0 for unlimited.
          </p>
          <div style={{ marginTop: 16 }}>
            <button className="btn" onClick={handleCreate}>Create Key</button>
            <button className="btn btn-outline" style={{ marginLeft: 8 }} onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className="btn" onClick={() => setShowCreate(true)}>+ Create New Key</button>
      )}

      {/* Key list */}
      <div style={{ marginTop: 16 }}>
        {keys.length === 0 ? (
          <div className="card">
            <p className="dim">No API keys yet. Create one to start using the API.</p>
          </div>
        ) : (
          keys.map(k => (
            <div className="card" key={k.key_id} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <div>
                  <h3 style={{ color: '#5ce1ff', marginBottom: 4 }}>{k.name || 'unnamed'}</h3>
                  <p className="dim" style={{ fontSize: 11 }}>ID: {k.key_id}</p>
                  <p className="dim" style={{ fontSize: 11 }}>Created: {fmtTime(k.created_at)}</p>
                </div>
                <button
                  className="btn btn-outline"
                  style={{ color: '#ff3b3b', borderColor: '#ff3b3b' }}
                  onClick={() => handleDelete(k.key_id)}
                >
                  revoke
                </button>
              </div>
              {/* Budget progress bar */}
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span className="dim">
                    {k.budget_cents > 0 ? fmtUSD(k.spent_cents) + ' / ' + fmtUSD(k.budget_cents) : fmtUSD(k.spent_cents) + ' (unlimited)'}
                  </span>
                  <span className="dim">
                    {k.budget_cents > 0 ? `${Math.round((k.spent_cents / k.budget_cents) * 100)}%` : '∞'}
                  </span>
                </div>
                <div style={{ background: '#1a1a1a', height: 6, borderRadius: 3, marginTop: 4, overflow: 'hidden' }}>
                  <div style={{
                    background: k.budget_cents > 0 && k.spent_cents >= k.budget_cents ? '#ff3b3b' : '#00ff9c',
                    height: '100%', width: k.budget_cents > 0
                      ? `${Math.min(100, (k.spent_cents / k.budget_cents) * 100)}%`
                      : '0%',
                  }} />
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

const inputStyle = {
  width: '100%' as const,
  padding: 8,
  background: '#0a0a0a',
  border: '1px solid #2a2a2a',
  borderRadius: 4,
  color: '#e0e0e0',
  fontFamily: 'monospace' as const,
  fontSize: 13,
}
