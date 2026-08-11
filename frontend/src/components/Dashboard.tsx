import { useState, useEffect } from 'react'
import { useAuthFetch, fmtUSD, shortAddr } from '../lib'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid,
} from 'recharts'

interface Stats {
  total_spend_cents: number
  total_requests: number
  total_input_tokens: number
  total_output_tokens: number
  marketplace_savings_cents: number
  top_models: { model: string, requests: number, spend_cents: number }[]
  top_api_keys: { name: string, requests: number, spend_cents: number }[]
  daily_spend: { day: string, spend_cents: number, requests: number }[]
  wallet_address: string
  balances: { eth: string, usdc: string, usdc_atomic: number }
}

const PIE_COLORS = ['#00ff9c', '#5ce1ff', '#ffd23f', '#ff3b3b', '#888888']

export function Dashboard({ walletAddress, balances, onNavigate }: {
  walletAddress: string
  balances: any
  onNavigate: (p: any) => void
}) {
  const authFetch = useAuthFetch()
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch('/api/user/dashboard')
        if (res.ok) {
          const data = await res.json()
          setStats(data)
        }
      } catch (e) {
        console.error('dashboard fetch failed', e)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  if (loading) {
    return (
      <div className="card" style={{ textAlign: 'center' }}>
        <span className="pulse-dot" /> <span className="dim">syncing dashboard data...</span>
      </div>
    )
  }

  const usdcBalance = balances ? (balances.usdc_atomic / 1e6).toFixed(6) : '0.00'
  const totalTokens = (stats?.total_input_tokens || 0) + (stats?.total_output_tokens || 0)

  return (
    <div>
      {/* Header with prompt symbol */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, marginBottom: 4 }}>
          <span style={{ color: 'var(--text-faint)' }}>▶</span> dashboard
        </h1>
        <p className="sub" style={{ marginBottom: 0 }}>
          <span className="faint">real-time usage · </span>
          <span style={{ color: 'var(--green)' }}>{stats?.total_requests || 0}</span>
          <span className="faint"> requests processed</span>
        </p>
      </div>

      {/* ── Bento grid: primary stat cards ────────────────────────────── */}
      <div className="bento">
        {/* Total spend — big card */}
        <div className="card span-2" style={{ padding: 24 }}>
          <p className="faint" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 8 }}>
            total spend
          </p>
          <p style={{
            fontSize: 36, fontWeight: 800, color: 'var(--green)',
            textShadow: 'var(--glow-green)', fontFamily: 'var(--font-mono)',
          }}>
            {fmtUSD(stats?.total_spend_cents || 0)}
          </p>
          <p className="faint" style={{ fontSize: 11, marginTop: 4 }}>settled in usdc on base</p>
        </div>

        {/* USDC balance */}
        <div className="card" style={{ padding: 24 }}>
          <p className="faint" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 8 }}>
            wallet balance
          </p>
          <p style={{ fontSize: 28, fontWeight: 800, color: 'var(--cyan)', textShadow: 'var(--glow-cyan)' }}>
            ${usdcBalance}
          </p>
          <p className="faint" style={{ fontSize: 11, marginTop: 4 }}>usdc · {shortAddr(walletAddress)}</p>
        </div>

        {/* Marketplace savings */}
        <div className="card" style={{ padding: 24, border: '1px solid rgba(0,255,156,0.2)' }}>
          <p className="faint" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 8 }}>
            you saved
          </p>
          <p style={{ fontSize: 28, fontWeight: 800, color: 'var(--green)' }}>
            {fmtUSD(stats?.marketplace_savings_cents || 0)}
          </p>
          <p className="faint" style={{ fontSize: 11, marginTop: 4 }}>vs openai pricing</p>
        </div>
      </div>

      {/* ── Secondary stat cards row ─────────────────────────────────── */}
      <div className="bento">
        <div className="card" style={{ textAlign: 'center', padding: 16 }}>
          <p className="faint" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>requests</p>
          <p style={{ fontSize: 22, fontWeight: 700, color: 'var(--cyan)' }}>{stats?.total_requests || 0}</p>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: 16 }}>
          <p className="faint" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>tokens in</p>
          <p style={{ fontSize: 22, fontWeight: 700, color: 'var(--cyan)' }}>{formatTokens(stats?.total_input_tokens || 0)}</p>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: 16 }}>
          <p className="faint" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>tokens out</p>
          <p style={{ fontSize: 22, fontWeight: 700, color: 'var(--cyan)' }}>{formatTokens(stats?.total_output_tokens || 0)}</p>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: 16 }}>
          <p className="faint" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>token vol</p>
          <p style={{ fontSize: 22, fontWeight: 700, color: 'var(--amber)' }}>{formatTokens(totalTokens)}</p>
        </div>
      </div>

      {/* ── Daily spend chart — full width ───────────────────────────── */}
      <div className="card" style={{ marginBottom: 12 }}>
        <h2>━━ daily spend · 30 days</h2>
        {(stats?.daily_spend?.length || 0) > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={stats!.daily_spend.map(d => ({ ...d, spend_usd: d.spend_cents / 100 }))}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="var(--text-faint)" fontSize={10} tickLine={false} />
              <YAxis stroke="var(--text-faint)" fontSize={11} tickFormatter={(v) => `$${v}`} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: 'var(--bg)', border: '1px solid var(--border-bright)', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 12 }}
                labelStyle={{ color: 'var(--text-dim)' }}
                formatter={(v: any) => [`$${(v as number).toFixed(4)}`, 'spend']}
                cursor={{ fill: 'rgba(0,255,156,0.05)' }}
              />
              <Bar dataKey="spend_usd" fill="var(--green)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <p className="faint">no spend data yet — make your first request to populate charts</p>
            <button className="btn btn-outline" style={{ marginTop: 12 }} onClick={() => onNavigate('apikeys')}>create an api key →</button>
          </div>
        )}
      </div>

      {/* ── Charts row: top models + top api keys ───────────────────── */}
      <div className="bento">
        {/* Top models pie */}
        <div className="card span-2">
          <h2>━━ top models</h2>
          {(stats?.top_models?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={stats!.top_models.map(m => ({ name: m.model, value: m.spend_cents }))} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} innerRadius={40}>
                  {stats!.top_models.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v: any) => fmtUSD(v as number)} contentStyle={{ background: 'var(--bg)', border: '1px solid var(--border-bright)', fontFamily: 'var(--font-mono)' }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="faint">no model data yet</p>}
        </div>

        {/* Top api keys */}
        <div className="card span-2">
          <h2>━━ top api keys</h2>
          {(stats?.top_api_keys?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stats!.top_api_keys.map(k => ({ name: k.name, spend_usd: k.spend_cents / 100 }))} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis type="number" stroke="var(--text-faint)" fontSize={11} tickFormatter={(v) => `$${v}`} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" stroke="var(--text-faint)" fontSize={11} width={80} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: 'var(--bg)', border: '1px solid var(--border-bright)', fontFamily: 'var(--font-mono)' }} formatter={(v: any) => [`$${(v as number).toFixed(2)}`, 'spend']} cursor={{ fill: 'rgba(92,225,255,0.05)' }} />
                <Bar dataKey="spend_usd" fill="var(--cyan)" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="faint">no api key data yet</p>}
        </div>
      </div>

      {/* ── Quick actions ───────────────────────────────────────────── */}
      <div className="card" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <h2 style={{ margin: 0, marginRight: 'auto' }}>━━ quick actions</h2>
        <button className="btn" onClick={() => onNavigate('apikeys')}>+ create api key</button>
        <button className="btn btn-outline" onClick={() => onNavigate('wallet')}>add funds →</button>
        <button className="btn btn-outline" onClick={() => onNavigate('activity')}>view activity →</button>
      </div>
    </div>
  )
}

function formatTokens(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return String(n)
}
