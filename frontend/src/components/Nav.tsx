import { shortAddr } from '../lib'
import type { Page } from '../App'
import type { ReactNode } from 'react'

const DASH_PAGES: { id: Page, label: string, icon: string }[] = [
  { id: 'dashboard', label: 'overview', icon: '◆' },
  { id: 'wallet', label: 'wallet', icon: '◈' },
  { id: 'apikeys', label: 'api keys', icon: '🔑' },
  { id: 'activity', label: 'activity', icon: '◉' },
  { id: 'usage', label: 'usage', icon: '≡' },
]

// All other site pages — accessible even after login. docs is emphasized.
const SITE_PAGES: { path: string, label: string, emphasize?: boolean }[] = [
  { path: '/', label: 'home' },
  { path: '/docs', label: 'docs', emphasize: true },
  { path: '/status', label: 'status' },
  { path: '/connect', label: 'connect' },
  { path: '/builder', label: 'builder' },
  { path: '/free-models', label: 'free models' },
  { path: '/health', label: 'health board' },
  { path: '/performance', label: 'verified tps' },
  { path: '/auction', label: 'cache auction' },
  { path: '/features', label: 'updates' },
  { path: '/top', label: 'top models' },
  { path: '/find', label: 'find model' },
  { path: '/compare', label: 'compare' },
  { path: '/playground', label: 'playground' },
  { path: '/about', label: 'about' },
]

// Simulated live ticker — in production this fetches from /api/health-board
const TICKER_ITEMS = [
  { label: 'surp/free', val: '$0.00', trend: 'free' },
  { label: 'surp/best-chat', val: '$0.012', trend: '↓' },
  { label: 'surp/best-coding', val: '$0.034', trend: '↑' },
  { label: 'usdc/base', val: '$1.00', trend: '—' },
  { label: 'tps', val: '847', trend: '↑' },
  { label: 'ttft', val: '120ms', trend: '↓' },
  { label: 'cache hit rate', val: '34%', trend: '↑' },
  { label: 'models live', val: '1,204', trend: '—' },
  { label: 'srp reward pool', val: '2.4M', trend: '↑' },
]

export function Nav({
  page, setPage, walletAddress, usdcBalance, onWalletClick, onLogout, children,
}: {
  page: Page
  setPage: (p: Page) => void
  walletAddress: string
  usdcBalance: string
  onWalletClick: () => void
  onLogout: () => void
  children: ReactNode
}) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Left sidebar — vertically stacked menu */}
      <aside style={{
        width: 240, flexShrink: 0,
        background: 'var(--bg)', borderRight: '1px solid var(--border)',
        padding: '20px 0', position: 'fixed', top: 0, bottom: 0, left: 0,
        overflowY: 'auto', zIndex: 50,
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Brand */}
        <div style={{ padding: '0 20px 20px', borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
          <a href="/" style={{ textDecoration: 'none', fontWeight: 800, fontSize: 20, color: 'var(--green)', textShadow: 'var(--glow-green)' }}>
            surp
          </a>
          <p className="faint" style={{ fontSize: 10, marginTop: 4 }}>surplus intelligence</p>
        </div>

        {/* Dashboard pages — account section */}
        <div style={{ padding: '0 12px 16px' }}>
          <p className="faint" style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 8, paddingLeft: 12 }}>
            ▸ account
          </p>
          {DASH_PAGES.map(p => (
            <button
              key={p.id}
              onClick={() => setPage(p.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left',
                background: page === p.id ? 'rgba(0,255,156,0.06)' : 'transparent',
                color: page === p.id ? 'var(--green)' : 'var(--text-dim)',
                border: 'none', borderLeft: page === p.id ? '2px solid var(--green)' : '2px solid transparent',
                padding: '9px 12px', borderRadius: 4, fontFamily: 'var(--font-mono)',
                fontSize: 13, cursor: 'pointer', marginBottom: 2,
                textShadow: page === p.id ? 'var(--glow-green)' : 'none',
              }}
            >
              <span style={{ width: 14, textAlign: 'center', opacity: 0.7 }}>{p.icon}</span>
              {p.label}
            </button>
          ))}
        </div>

        {/* Site pages — full site access */}
        <div style={{ padding: '0 12px', flex: 1 }}>
          <p className="faint" style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 8, marginTop: 8, paddingLeft: 12 }}>
            ▸ explore
          </p>
          {SITE_PAGES.map(p => (
            <a
              key={p.path}
              href={p.path}
              style={{
                display: 'block',
                color: p.emphasize ? 'var(--green)' : 'var(--text-dim)',
                fontWeight: p.emphasize ? 700 : 400,
                textDecoration: 'none',
                borderLeft: p.emphasize ? '2px solid var(--green)' : '2px solid transparent',
                padding: '7px 12px', borderRadius: 4, fontFamily: 'var(--font-mono)',
                fontSize: 13, marginBottom: 2,
              }}
            >
              {p.label}
              {p.emphasize && <span style={{ float: 'right', opacity: 0.7 }}>★</span>}
            </a>
          ))}
        </div>

        {/* Footer status */}
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', marginTop: 'auto' }}>
          <span className="pulse-dot" /> <span className="faint" style={{ fontSize: 10 }}>all systems nominal</span>
        </div>
      </aside>

      {/* Main content area */}
      <div style={{ marginLeft: 240, flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Live ticker bar — like a trading terminal */}
        <div style={{
          background: 'var(--bg-card)', borderBottom: '1px solid var(--border)',
          overflow: 'hidden', height: 32, display: 'flex', alignItems: 'center',
        }}>
          <div style={{
            padding: '0 12px', background: 'rgba(0,255,156,0.08)',
            borderRight: '1px solid var(--border)', height: '100%',
            display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
          }}>
            <span className="pulse-dot" />
            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--green)', letterSpacing: 1 }}>LIVE</span>
          </div>
          <div className="ticker-track" style={{ paddingLeft: 12 }}>
            {[...TICKER_ITEMS, ...TICKER_ITEMS].map((item, i) => (
              <span key={i} style={{ fontSize: 11, display: 'flex', gap: 6, alignItems: 'center' }}>
                <span className="faint">{item.label}</span>
                <span style={{ color: 'var(--green)' }}>{item.val}</span>
                <span style={{ color: item.trend === '↑' ? 'var(--green)' : item.trend === '↓' ? 'var(--red)' : 'var(--text-faint)' }}>{item.trend}</span>
                <span style={{ color: 'var(--border-bright)' }}>│</span>
              </span>
            ))}
          </div>
        </div>

        {/* Top bar with wallet widget + logout */}
        <header style={{
          position: 'sticky', top: 0, zIndex: 40,
          background: 'rgba(0,0,0,0.9)', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 24px', backdropFilter: 'blur(8px)',
        }}>
          <span className="faint" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 }}>
            ▸ {DASH_PAGES.find(p => p.id === page)?.label}
          </span>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Wallet widget — top right */}
            <button
              onClick={onWalletClick}
              style={{
                background: 'var(--bg-card)', border: '1px solid var(--green)',
                color: 'var(--green)', padding: '7px 14px', borderRadius: 16,
                fontFamily: 'var(--font-mono)', fontSize: 12, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 8,
                transition: 'box-shadow 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.boxShadow = 'var(--glow-green)'}
              onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
              title="view wallet"
            >
              <span style={{ fontWeight: 700, textShadow: 'var(--glow-green)' }}>${usdcBalance}</span>
              <span style={{ color: 'var(--text-faint)' }}>│</span>
              <span className="faint">{shortAddr(walletAddress)}</span>
            </button>

            <button
              onClick={onLogout}
              style={{
                background: 'transparent', border: '1px solid var(--border-bright)',
                color: 'var(--text-dim)', padding: '7px 14px', borderRadius: 4,
                fontFamily: 'var(--font-mono)', fontSize: 12, cursor: 'pointer',
              }}
            >
              logout
            </button>
          </div>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, padding: '24px', maxWidth: 1200, width: '100%', margin: '0 auto' }}>
          {children}
        </main>
      </div>
    </div>
  )
}
