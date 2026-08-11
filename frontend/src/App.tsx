import { usePrivy, useWallets } from '@privy-io/react-auth'
import { useState, useEffect, useCallback } from 'react'
import {
  Dashboard,
  ApiKeys,
  Activity,
  Usage,
  WalletPage,
  LoginScreen,
  Nav,
  Studio,
} from './components'

export type Page = 'dashboard' | 'wallet' | 'apikeys' | 'activity' | 'usage' | 'studio'

export default function App() {
  const { ready, authenticated, user, logout, login, getAccessToken } = usePrivy()
  const { wallets } = useWallets()
  const [page, setPage] = useState<Page>('dashboard')
  const [balances, setBalances] = useState<{eth: string, usdc: string, usdc_atomic: number} | null>(null)

  const activeWallet = wallets[0]
  const walletAddress = activeWallet?.address || ''

  // Fetch balances when wallet is available
  const refreshBalances = useCallback(async () => {
    try {
      const token = await getAccessToken()
      if (!token) return
      const res = await fetch('/api/user/balances', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setBalances(data)
      }
    } catch (e) {
      console.error('balance fetch failed', e)
    }
  }, [getAccessToken])

  useEffect(() => {
    if (authenticated && walletAddress) {
      refreshBalances()
      const interval = setInterval(refreshBalances, 30000) // refresh every 30s
      return () => clearInterval(interval)
    }
  }, [authenticated, walletAddress, refreshBalances])

  // Wait for Privy to be ready
  if (!ready) {
    return (
      <div className="container">
        <div className="card"><h2>Loading...</h2><p className="dim">Connecting to Privy</p></div>
      </div>
    )
  }

  // Not authenticated — show login
  if (!authenticated) {
    return <LoginScreen onLogin={() => login()} />
  }

  const usdcBalance = balances ? (balances.usdc_atomic / 1e6).toFixed(6) : '0.00'

  // Render the page content based on current selection
  const pageContent = (
    <>
      {page === 'dashboard' && (
        <Dashboard walletAddress={walletAddress} balances={balances} onNavigate={setPage} />
      )}
      {page === 'wallet' && (
        <WalletPage
          walletAddress={walletAddress}
          balances={balances}
          onRefresh={refreshBalances}
        />
      )}
      {page === 'apikeys' && <ApiKeys />}
      {page === 'activity' && <Activity />}
      {page === 'usage' && <Usage />}
      {page === 'studio' && <Studio />}
    </>
  )

  return (
    <Nav
      page={page}
      setPage={setPage}
      walletAddress={walletAddress}
      usdcBalance={usdcBalance}
      onWalletClick={() => setPage('wallet')}
      onLogout={logout}
    >
      {pageContent}
    </Nav>
  )
}
