import { useState, useEffect } from 'react'
import { useAuthFetch, fmtUSD, fmtTime, shortAddr } from '../lib'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, PieChart, Pie, Cell, Legend,
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

  if (loading) return <div className="card"><h2>Loading dashboard...</h2></div>

  const usdcBalance = balances ? (balances.usdc_atomic / 1e6).toFixed(6) : '0.00'

  return (
    <div>
      <h1>Dashboard</h1>
      <p className="sub">your usage overview</p>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 24 }}>
        <StatCard label="Total Spend" value={fmtUSD(stats?.total_spend_cents || 0)} color="#00ff9c" />
        <StatCard label="USDC Balance" value={`$${usdcBalance}`} color="#5ce1ff" />
        <StatCard label="Requests" value={String(stats?.total_requests || 0)} color="#ffd23f" />
        <StatCard label="Token Volume" value={formatTokens((stats?.total_input_tokens || 0) + (stats?.total_output_tokens || 0))} color="#5ce1ff" />
        <StatCard label="Marketplace Savings" value={fmtUSD(stats?.marketplace_savings_cents || 0)} color="#00ff9c" />
      </div>

      {/* Daily spend chart */}
      <div className="card">
        <h2>Daily Spend (30 days)</h2>
        {(stats?.daily_spend?.length || 0) > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={stats!.daily_spend.map(d => ({ ...d, spend_usd: d.spend_cents / 100 }))}>
              <CartesianGrid stroke="#1a1a1a" strokeDasharray="3 3" />
              <XAxis dataKey="day" stroke="#888" fontSize={10} />
              <YAxis stroke="#888" fontSize={11} tickFormatter={(v) => `$${v}`} />
              <Tooltip
                contentStyle={{ background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 4 }}
                labelStyle={{ color: '#888' }}
                formatter={(v: any) => [`$${(v as number).toFixed(2)}`, 'spend']}
              />
              <Bar dataKey="spend_usd" fill="#00ff9c" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="dim">No spend data yet — make your first request to see charts.</p>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        {/* Top models pie */}
        <div className="card">
          <h2>Top Models</h2>
          {(stats?.top_models?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={stats!.top_models.map(m => ({ name: m.model, value: m.spend_cents }))} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                  {stats!.top_models.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v: any) => fmtUSD(v as number)} contentStyle={{ background: '#0a0a0a', border: '1px solid #1a1a1a' }} />
                <Legend formatter={(v) => <span style={{ color: '#888', fontSize: 11 }}>{v}</span>} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="dim">No model data yet.</p>}
        </div>

        {/* Top API keys */}
        <div className="card">
          <h2>Top API Keys</h2>
          {(stats?.top_api_keys?.length || 0) > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stats!.top_api_keys.map(k => ({ name: k.name, requests: k.requests, spend_usd: k.spend_cents / 100 }))} layout="vertical">
                <CartesianGrid stroke="#1a1a1a" strokeDasharray="3 3" />
                <XAxis type="number" stroke="#888" fontSize={11} tickFormatter={(v) => `$${v}`} />
                <YAxis type="category" dataKey="name" stroke="#888" fontSize={11} width={80} />
                <Tooltip contentStyle={{ background: '#0a0a0a', border: '1px solid #1a1a1a' }} formatter={(v: any) => [`$${(v as number).toFixed(2)}`, 'spend']} />
                <Bar dataKey="spend_usd" fill="#5ce1ff" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="dim">No API key data yet.</p>}
        </div>
      </div>

      {/* Wallet section */}
      <div className="card" style={{ marginTop: 16 }}>
        <h2>Your Wallet</h2>
        <p className="dim">Embedded wallet address</p>
        <div className="wallet-addr">{walletAddress}</div>
        <button className="btn btn-outline" onClick={() => onNavigate('wallet')}>Manage Wallet →</button>
      </div>

      {/* Quick start */}
      <div className="card">
        <h2>Quick Start</h2>
        <p className="dim" style={{ marginBottom: 12 }}>Create an API key, fund your wallet, then make your first request:</p>
        <button className="btn" onClick={() => onNavigate('apikeys')}>Create API Key →</button>
        <button className="btn btn-outline" style={{ marginLeft: 8 }} onClick={() => onNavigate('wallet')}>Add Funds →</button>
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string, value: string, color: string }) {
  return (
    <div className="card" style={{ textAlign: 'center', padding: 16 }}>
      <p className="dim" style={{ fontSize: 11, marginBottom: 4 }}>{label}</p>
      <p style={{ fontSize: 22, fontWeight: 'bold', color }}>{value}</p>
    </div>
  )
}

function formatTokens(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return String(n)
}
