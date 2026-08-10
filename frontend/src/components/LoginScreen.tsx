export function LoginScreen({ onLogin }: { onLogin: () => void }) {
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
        <button className="btn" onClick={onLogin}>Login</button>
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
