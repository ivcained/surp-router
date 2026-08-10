import { shortAddr } from '../lib'
import type { Page } from '../App'
import type { ReactNode } from 'react'

const DASH_PAGES: { id: Page, label: string }[] = [
  { id: 'dashboard', label: 'overview' },
  { id: 'wallet', label: 'wallet' },
  { id: 'apikeys', label: 'API keys' },
  { id: 'activity', label: 'activity' },
  { id: 'usage', label: 'usage' },
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
  { path: '/performance', label: 'verified TPS' },
  { path: '/auction', label: 'cache auction' },
  { path: '/features', label: 'features & updates' },
  { path: '/top', label: 'top models' },
  { path: '/find', label: 'find model' },
  { path: '/compare', label: 'compare' },
  { path: '/playground', label: 'playground' },
  { path: '/about', label: 'about' },
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
        width: 220, flexShrink: 0,
        background: '#0a0a0a', borderRight: '1px solid #1a1a1a',
        padding: '20px 0', position: 'fixed', top: 0, bottom: 0, left: 0,
        overflowY: 'auto', zIndex: 50,
      }}>
        {/* Brand */}
        <div style={{ padding: '0 20px 24px', borderBottom: '1px solid #1a1a1a', marginBottom: 16 }}>
          <a href="/" style={{ textDecoration: 'none', fontWeight: 'bold', fontSize: 18, color: '#00ff9c' }}>
            surp
          </a>
          <p className="dim" style={{ fontSize: 10, marginTop: 4 }}>ivc.lol</p>
        </div>

        {/* Dashboard pages — account section */}
        <div style={{ padding: '0 12px 16px' }}>
          <p className="dim" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, paddingLeft: 8 }}>
            account
          </p>
          {DASH_PAGES.map(p => (
            <button
              key={p.id}
              onClick={() => setPage(p.id)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                background: page === p.id ? '#00ff9c22' : 'transparent',
                color: page === p.id ? '#00ff9c' : '#888',
                border: 'none', borderLeft: page === p.id ? '3px solid #00ff9c' : '3px solid transparent',
                padding: '8px 12px', borderRadius: 4, fontFamily: 'inherit',
                fontSize: 13, cursor: 'pointer', marginBottom: 2,
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Site pages — full site access */}
        <div style={{ padding: '0 12px' }}>
          <p className="dim" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, marginTop: 16, paddingLeft: 8 }}>
            explore
          </p>
          {SITE_PAGES.map(p => (
            <a
              key={p.path}
              href={p.path}
              style={{
                display: 'block',
                color: p.emphasize ? '#00ff9c' : '#888',
                fontWeight: p.emphasize ? 'bold' : 'normal',
                textDecoration: 'none',
                borderLeft: p.emphasize ? '3px solid #00ff9c' : '3px solid transparent',
                padding: '8px 12px', borderRadius: 4, fontFamily: 'inherit',
                fontSize: 13, marginBottom: 2,
              }}
            >
              {p.label}
              {p.emphasize && <span style={{ float: 'right', opacity: 0.6 }}>★</span>}
            </a>
          ))}
        </div>
      </aside>

      {/* Main content area */}
      <div style={{ marginLeft: 220, flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Top bar with wallet widget + logout */}
        <header style={{
          position: 'sticky', top: 0, zIndex: 40,
          background: 'rgba(0,0,0,0.9)', borderBottom: '1px solid #1a1a1a',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 24px', backdropFilter: 'blur(8px)',
        }}>
          <span className="dim" style={{ fontSize: 12 }}>
            {DASH_PAGES.find(p => p.id === page)?.label || 'dashboard'}
          </span>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Wallet widget — top right */}
            <button
              onClick={onWalletClick}
              style={{
                background: '#0a0a0a', border: '1px solid #00ff9c',
                color: '#00ff9c', padding: '6px 12px', borderRadius: 16,
                fontFamily: 'monospace', fontSize: 12, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 8,
              }}
              title="view wallet"
            >
              <span style={{ fontWeight: 'bold' }}>${usdcBalance}</span>
              <span style={{ color: '#888' }}>|</span>
              <span>{shortAddr(walletAddress)}</span>
            </button>

            <button
              onClick={onLogout}
              style={{
                background: 'transparent', border: '1px solid #2a2a2a',
                color: '#888', padding: '6px 12px', borderRadius: 4,
                fontFamily: 'inherit', fontSize: 12, cursor: 'pointer',
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

export function WalletWidget({ walletAddress, usdcBalance }: { walletAddress: string, usdcBalance: string }) {
  return (
    <div style={{
      background: '#0a0a0a', border: '1px solid #00ff9c',
      color: '#00ff9c', padding: '6px 12px', borderRadius: 16,
      fontFamily: 'monospace', fontSize: 12,
      display: 'flex', alignItems: 'center', gap: 8,
    }}>
      <span style={{ fontWeight: 'bold' }}>${usdcBalance}</span>
      <span style={{ color: '#888' }}>|</span>
      <span>{shortAddr(walletAddress)}</span>
    </div>
  )
}
