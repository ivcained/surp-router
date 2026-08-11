import { useState, useEffect } from 'react'
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

// All other site pages — split into evenly-distributed labeled sections.
// Mobile shows the same sidebar as an off-canvas drawer (hamburger toggle).
const SITE_SECTIONS: { label: string, pages: { path: string, label: string, emphasize?: boolean }[] }[] = [
  {
    label: 'discover',
    pages: [
      { path: '/', label: 'home' },
      { path: '/docs', label: 'docs', emphasize: true },
      { path: '/about', label: 'about' },
    ],
  },
  {
    label: 'build',
    pages: [
      { path: '/connect', label: 'connect' },
      { path: '/builder', label: 'builder' },
      { path: '/playground', label: 'playground' },
      { path: '/compare', label: 'compare' },
      { path: '/find', label: 'find model' },
    ],
  },
  {
    label: 'models & pricing',
    pages: [
      { path: '/top', label: 'top models' },
      { path: '/free-models', label: 'free models' },
      { path: '/auction', label: 'cache auction' },
    ],
  },
  {
    label: 'monitor',
    pages: [
      { path: '/status', label: 'status' },
      { path: '/health', label: 'health board' },
      { path: '/performance', label: 'verified tps' },
      { path: '/features', label: 'updates' },
    ],
  },
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
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Current path — used to light up the matching site link (explore section).
  // The account pages (overview/wallet/etc.) are SPA state, highlighted by `page`.
  const currentPathname = (typeof window !== 'undefined' ? window.location.pathname : '/').replace(/\/$/, '') || '/'
  const isActivePath = (href: string) => (href === '/' ? currentPathname === '/' : currentPathname.startsWith(href))

  // Close drawer on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrawerOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Backdrop — mobile only */}
      {drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 59,
            background: 'rgba(0,0,0,0.7)',
          }}
        />
      )}

      {/* Left sidebar — vertically stacked menu, off-canvas on mobile */}
      <aside
        className={drawerOpen ? 'sidebar-open' : ''}
        style={{
          width: 240, flexShrink: 0,
          background: 'var(--bg)', borderRight: '1px solid var(--border)',
          padding: '20px 0', position: 'fixed', top: 0, bottom: 0, left: 0,
          overflowY: 'auto', zIndex: 60,
          display: 'flex', flexDirection: 'column',
          transition: 'transform 0.25s ease',
        }}
      >
        {/* Brand */}
        <div style={{ padding: '0 20px 20px', borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
          <a href="/" style={{ textDecoration: 'none', fontWeight: 800, fontSize: 20, color: 'var(--green)', textShadow: 'var(--glow-green)' }}>
            surp
          </a>
          <p className="faint" style={{ fontSize: 10, marginTop: 4 }}>surplus intelligence router</p>
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
                background: page === p.id ? 'linear-gradient(90deg, rgba(0,255,156,0.14), rgba(0,255,156,0.03))' : 'transparent',
                color: page === p.id ? 'var(--green)' : 'var(--text-dim)',
                border: 'none', borderLeft: page === p.id ? '2px solid var(--green)' : '2px solid transparent',
                padding: '9px 12px', borderRadius: 4, fontFamily: 'var(--font-mono)',
                fontSize: 13, cursor: 'pointer', marginBottom: 2,
                textShadow: page === p.id ? '0 0 8px rgba(0,255,156,0.55)' : 'none',
                boxShadow: page === p.id ? 'inset 0 0 12px rgba(0,255,156,0.12), 0 0 10px rgba(0,255,156,0.18)' : 'none',
                fontWeight: page === p.id ? 700 : 400,
              }}
            >
              <span style={{ width: 14, textAlign: 'center', opacity: 0.7 }}>{p.icon}</span>
              {p.label}
            </button>
          ))}
        </div>

        {/* Site pages — full site access, evenly distributed into sections */}
        <div style={{ padding: '0 12px', flex: 1 }}>
          {SITE_SECTIONS.map((section, si) => (
            <div key={section.label}>
              <p className="faint" style={{
                fontSize: 9, textTransform: 'uppercase', letterSpacing: 1.5,
                marginBottom: 8, marginTop: si === 0 ? 8 : 18, paddingLeft: 12,
              }}>
                ▸ {section.label}
              </p>
              {section.pages.map(p => {
                const isActive = isActivePath(p.path)
                return (
                <a
                  key={p.path}
                  href={p.path}
                  className={isActive ? 'nav-item-active' : ''}
                  style={{
                    display: 'block',
                    color: isActive ? 'var(--green)' : p.emphasize ? 'var(--green)' : 'var(--text-dim)',
                    fontWeight: isActive ? 700 : p.emphasize ? 700 : 400,
                    textDecoration: 'none',
                    borderLeft: isActive || p.emphasize ? '2px solid var(--green)' : '2px solid transparent',
                    padding: '7px 12px', borderRadius: 4, fontFamily: 'var(--font-mono)',
                    fontSize: 13, marginBottom: 2,
                    background: isActive ? 'linear-gradient(90deg, rgba(0,255,156,0.14), rgba(0,255,156,0.03))' : 'transparent',
                    boxShadow: isActive ? 'inset 0 0 12px rgba(0,255,156,0.12), 0 0 10px rgba(0,255,156,0.18)' : 'none',
                    textShadow: isActive ? '0 0 8px rgba(0,255,156,0.55)' : 'none',
                  }}
                >
                  {p.label}
                  {p.emphasize && <span style={{ float: 'right', opacity: 0.7 }}>★</span>}
                </a>
              )})}
            </div>
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

        {/* Top bar with wallet widget + logout.
            On mobile the top bar wraps: wallet stays on row 1, logout
            drops to row 2 below it so it never overflows the viewport. */}
        <header className="dash-topbar">
          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button
              className="site-hamburger"
              onClick={() => setDrawerOpen(true)}
              aria-label="open menu"
              style={{
                display: 'none', width: 36, height: 36, alignItems: 'center', justifyContent: 'center',
                background: 'transparent', border: '1px solid var(--border-bright)', borderRadius: 4,
                color: 'var(--green)', cursor: 'pointer', padding: 0, fontSize: 18, lineHeight: 1,
              }}
            >≡</button>
            <span className="faint dash-breadcrumb" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 }}>
              ▸ {DASH_PAGES.find(p => p.id === page)?.label}
            </span>
          </span>

          <div className="dash-actions">
            {/* Wallet widget — balance + address */}
            <button
              className="dash-wallet"
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
              className="dash-logout"
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
