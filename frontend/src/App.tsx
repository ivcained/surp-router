import { usePrivy, useWallets } from '@privy-io/react-auth'
import { useState } from 'react'

export default function App() {
  const { ready, authenticated, user, logout, login } = usePrivy()
  const { wallets } = useWallets()
  const [copied, setCopied] = useState(false)

  // Wait for Privy to be ready before rendering anything.
  if (!ready) {
    return (
      <div className="container">
        <div className="card">
          <h2>Loading...</h2>
          <p className="dim">Connecting to Privy</p>
        </div>
      </div>
    )
  }

  // Not authenticated — show the login card.
  if (!authenticated) {
    return (
      <div className="container">
        <h1>surp</h1>
        <p className="sub">cheapest LLM inference on the internet — login to create your wallet</p>

        <div className="card">
          <h2>Login</h2>
          <p className="dim" style={{ marginBottom: 16 }}>
            Login with email, passkey, or Farcaster. An embedded wallet is created
            automatically on your first login — you can use it to pay for
            inference with USDC on Base.
          </p>

          {/* Privy's login() hook triggers the full auth flow.
              Login methods (email/passkey/Farcaster) are configured in the
              Privy dashboard, so this one button surfaces all enabled methods. */}
          <button
            onClick={() => login()}
            style={{
              background: '#00ff9c',
              color: '#000',
              border: 'none',
              borderRadius: '4px',
              padding: '12px 24px',
              fontFamily: 'inherit',
              fontSize: '14px',
              fontWeight: 'bold',
              cursor: 'pointer',
            }}
          >
            Login
          </button>
          <p className="dim" style={{ marginTop: 16, fontSize: 12 }}>
            By logging in you agree to the surp terms. Your wallet is non-custodial —
            only you control the keys.
          </p>
        </div>

        <div className="card">
          <h2>Why login?</h2>
          <ul style={{ paddingLeft: 20, lineHeight: 1.8 }}>
            <li>Get a free embedded wallet — no browser extension needed</li>
            <li>Pay per LLM request in USDC on Base (x402 protocol)</li>
            <li>Track usage and spend across all your sessions</li>
            <li>Earn SRP rewards for cache hits and referrals</li>
          </ul>
        </div>

        <p className="dim" style={{ marginTop: 24 }}>
          <a href="/">← back to surp.ivc.lol</a>
        </p>
      </div>
    )
  }

  // Authenticated — show the wallet dashboard.
  const activeWallet = wallets[0]
  const walletAddress = activeWallet?.address

  const copyAddress = () => {
    if (walletAddress) {
      navigator.clipboard.writeText(walletAddress)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="container">
      <h1>surp</h1>
      <p className="sub">your wallet &amp; usage</p>

      {/* User info card */}
      <div className="card">
        <h2>Account</h2>
        <p className="dim" style={{ marginBottom: 8 }}>Logged in as</p>
        <p style={{ fontSize: 16 }}>
          {user?.email?.address || user?.farcaster?.username || user?.wallet?.address?.slice(0, 8) + '...' || 'user'}
        </p>
        <div style={{ marginTop: 12 }}>
          <span className="badge badge-green">✓ authenticated</span>
          {' '}
          <span className="badge badge-dim">non-custodial</span>
        </div>
        <button
          className="btn btn-outline"
          style={{ marginTop: 16 }}
          onClick={() => logout()}
        >
          Logout
        </button>
      </div>

      {/* Embedded wallet card */}
      <div className="card">
        <h2>Your Wallet</h2>
        {activeWallet ? (
          <>
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="badge badge-green">
                {activeWallet.walletClientType}
              </span>
              <span className="badge badge-dim">Base</span>
            </div>
            <p className="dim" style={{ marginBottom: 4 }}>Wallet address</p>
            <div className="wallet-addr">{walletAddress}</div>
            <button className="btn btn-outline" onClick={copyAddress}>
              {copied ? '✓ copied' : 'copy address'}
            </button>
            <p className="dim" style={{ marginTop: 16, fontSize: 12 }}>
              This is your non-custodial embedded wallet. Fund it with USDC on Base
              to pay for inference — each request settles via the x402 protocol.
              You can export the private key from the Privy dashboard if you ever
              want to move this wallet elsewhere.
            </p>
          </>
        ) : (
          <p className="dim">Creating your embedded wallet...</p>
        )}
      </div>

      {/* Quick start card */}
      <div className="card">
        <h2>Make your first request</h2>
        <p className="dim" style={{ marginBottom: 12 }}>
          Once your wallet is funded with USDC, try a request:
        </p>
        <pre style={{
          background: '#0a0a0a', padding: 12, borderRadius: 4,
          border: '1px solid #1a1a1a', overflowX: 'auto', fontSize: 12
        }}>
{`curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"surp/best-chat",
       "messages":[{"role":"user","content":"Hello"}],
       "max_tokens":50}'`}
        </pre>
        <p className="dim" style={{ marginTop: 12, fontSize: 12 }}>
          The first request returns 402 Payment Required. Your wallet signs a
          USDC transfer and retries — the response streams back within seconds.
        </p>
      </div>

      <p className="dim" style={{ marginTop: 24 }}>
        <a href="/">← back to surp.ivc.lol</a>
      </p>
    </div>
  )
}
