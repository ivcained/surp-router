import { useState } from 'react'
import { useAuthFetch, shortAddr } from '../lib'
import { QRCodeSVG } from 'qrcode.react'

export function WalletPage({ walletAddress, balances, onRefresh }: {
  walletAddress: string
  balances: any
  onRefresh: () => void
}) {
  const authFetch = useAuthFetch()
  const [tab, setTab] = useState<'overview' | 'add' | 'withdraw'>('overview')
  const [withdrawTo, setWithdrawTo] = useState('')
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [withdrawStatus, setWithdrawStatus] = useState('')
  const [copied, setCopied] = useState(false)

  const usdcBalance = balances ? (balances.usdc_atomic / 1e6).toFixed(6) : '0.00'
  const ethBalance = balances ? (parseInt(balances.eth) / 1e18).toFixed(6) : '0.00'

  const copyAddress = () => {
    navigator.clipboard.writeText(walletAddress)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleWithdraw = async () => {
    setWithdrawStatus('Submitting...')
    try {
      const res = await authFetch('/api/user/withdraw', {
        method: 'POST',
        body: JSON.stringify({ to: withdrawTo, amount: withdrawAmount }),
      })
      const data = await res.json()
      if (res.ok) {
        setWithdrawStatus(data.message || 'Withdrawal initiated — sign in your wallet')
      } else {
        setWithdrawStatus(`Error: ${data.error}`)
      }
    } catch (e: any) {
      setWithdrawStatus(`Error: ${e.message}`)
    }
  }

  return (
    <div>
      <h1>Wallet</h1>
      <p className="sub">manage your USDC balance</p>

      {/* Balance cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <p className="dim" style={{ fontSize: 11 }}>USDC Balance</p>
          <p style={{ fontSize: 28, fontWeight: 'bold', color: '#00ff9c' }}>${usdcBalance}</p>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <p className="dim" style={{ fontSize: 11 }}>ETH (gas)</p>
          <p style={{ fontSize: 28, fontWeight: 'bold', color: '#5ce1ff' }}>{ethBalance}</p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['overview', 'add', 'withdraw'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? 'btn' : 'btn btn-outline'}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="card">
          <h2>Wallet Address</h2>
          <div style={{ textAlign: 'center', padding: 20 }}>
            {walletAddress && (
              <div style={{ background: '#fff', padding: 16, borderRadius: 8, display: 'inline-block' }}>
                <QRCodeSVG value={walletAddress} size={180} />
              </div>
            )}
          </div>
          <p className="dim">Your embedded wallet address (Base network)</p>
          <div className="wallet-addr">{walletAddress}</div>
          <button className="btn btn-outline" onClick={copyAddress}>
            {copied ? '✓ copied' : 'copy address'}
          </button>
          <button className="btn" style={{ marginLeft: 8 }} onClick={onRefresh}>refresh balance</button>
        </div>
      )}

      {tab === 'add' && (
        <div className="card">
          <h2>Add Funds (USDC on Base)</h2>
          <p className="dim" style={{ marginBottom: 16 }}>
            Send USDC on the <strong>Base</strong> network to your surp wallet address below.
            Do not send to other networks — only Base USDC will arrive.
          </p>

          <div style={{ textAlign: 'center', padding: 16, background: '#fff', borderRadius: 8, display: 'inline-block', margin: '0 auto', display: 'block', width: 'fit-content' }}>
            {walletAddress && <QRCodeSVG value={walletAddress} size={200} />}
          </div>

          <p className="dim" style={{ marginTop: 16, marginBottom: 4 }}>Your deposit address</p>
          <div className="wallet-addr">{walletAddress}</div>
          <button className="btn btn-outline" onClick={copyAddress}>
            {copied ? '✓ copied' : 'copy address'}
          </button>

          <div style={{ marginTop: 24, padding: 16, background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 4 }}>
            <h3 style={{ color: '#5ce1ff', fontSize: 14, marginBottom: 12 }}>How to transfer USDC from Base</h3>
            <ol style={{ paddingLeft: 20, lineHeight: 2, fontSize: 13, color: '#e0e0e0' }}>
              <li>Open your external wallet (MetaMask, Coinbase Wallet, etc.)</li>
              <li>Make sure you're on the <strong style={{ color: '#00ff9c' }}>Base</strong> network</li>
              <li>Send USDC to your surp wallet address above</li>
              <li>Confirm the transaction — funds arrive in ~10 seconds</li>
              <li>Click "refresh balance" above to see your updated balance</li>
            </ol>
            <p className="dim" style={{ fontSize: 11, marginTop: 12 }}>
              USDC contract: <code style={{ color: '#888' }}>0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913</code>
            </p>
          </div>
        </div>
      )}

      {tab === 'withdraw' && (
        <div className="card">
          <h2>Withdraw USDC</h2>
          <p className="dim" style={{ marginBottom: 16 }}>
            Withdraw USDC from your surp wallet to an external address on Base.
          </p>
          <p className="dim">Available: <strong style={{ color: '#00ff9c' }}>${usdcBalance}</strong> USDC</p>

          <label className="dim" style={{ display: 'block', marginBottom: 4, marginTop: 16 }}>Destination address</label>
          <input
            type="text"
            value={withdrawTo}
            onChange={(e) => setWithdrawTo(e.target.value)}
            placeholder="0x..."
            style={{
              width: '100%', padding: 8, background: '#0a0a0a', border: '1px solid #2a2a2a',
              borderRadius: 4, color: '#e0e0e0', fontFamily: 'monospace', fontSize: 13,
            }}
          />

          <label className="dim" style={{ display: 'block', marginBottom: 4, marginTop: 12 }}>Amount (USDC)</label>
          <input
            type="text"
            value={withdrawAmount}
            onChange={(e) => setWithdrawAmount(e.target.value)}
            placeholder="1.50"
            style={{
              width: '100%', padding: 8, background: '#0a0a0a', border: '1px solid #2a2a2a',
              borderRadius: 4, color: '#e0e0e0', fontFamily: 'monospace', fontSize: 13,
            }}
          />

          <button
            className="btn"
            style={{ marginTop: 16 }}
            onClick={handleWithdraw}
            disabled={!withdrawTo || !withdrawAmount}
          >
            Withdraw
          </button>

          {withdrawStatus && (
            <p className="dim" style={{ marginTop: 12, padding: 8, background: '#0a0a0a', borderRadius: 4 }}>
              {withdrawStatus}
            </p>
          )}

          <p className="dim" style={{ marginTop: 16, fontSize: 11 }}>
            Withdrawals are signed by your embedded wallet and broadcast to Base.
            A small amount of ETH is required for gas.
          </p>
        </div>
      )}
    </div>
  )
}
