import { shortAddr, fmtUSD } from '../lib'
import type { Page } from '../App'

const PAGES: { id: Page, label: string }[] = [
  { id: 'dashboard', label: 'dashboard' },
  { id: 'wallet', label: 'wallet' },
  { id: 'apikeys', label: 'API keys' },
  { id: 'activity', label: 'activity' },
  { id: 'usage', label: 'usage' },
]

export function Nav({
  page, setPage, walletAddress, usdcBalance, onWalletClick, onLogout,
}: {
  page: Page
  setPage: (p: Page) => void
  walletAddress: string
  usdcBalance: string
  onWalletClick: () => void
  onLogout: () => void
}) {
  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.95)', borderBottom: '1px solid #1a1a1a',
      display: 'flex', alignItems: 'center', padding: '0 16px', height: 56,
      backdropFilter: 'blur(8px)',
    }}>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', flex: 1 }}>
        <a href="/" style={{ fontWeight: 'bold', color: '#00ff9c' }}>surp</a>
        {PAGES.map(p => (
          <button
            key={p.id}
            onClick={() => setPage(p.id)}
            style={{
              background: page === p.id ? '#00ff9c22' : 'transparent',
              color: page === p.id ? '#00ff9c' : '#888',
              border: 'none', padding: '4px 12px', borderRadius: 4,
              fontFamily: 'inherit', fontSize: 13, cursor: 'pointer',
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

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
        <span style={{ color: '#00ff9c', fontWeight: 'bold' }}>${usdcBalance}</span>
        <span style={{ color: '#888' }}>|</span>
        <span>{shortAddr(walletAddress)}</span>
      </button>

      <button
        onClick={onLogout}
        style={{
          background: 'transparent', border: '1px solid #2a2a2a',
          color: '#888', padding: '6px 12px', borderRadius: 4,
          fontFamily: 'inherit', fontSize: 12, cursor: 'pointer', marginLeft: 8,
        }}
      >
        logout
      </button>
    </nav>
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
