import { useState, useEffect } from 'react'

const BOOT_LINES = [
  '> surp-router v3.14 — surplus intelligence gateway',
  '> connecting to marketplace...        [ok]',
  '> loading cheapest-model routing...  [ok]',
  '> x402 payment facilitator...        [ok]',
  '> usdc/base settlement...            [ok]',
  '> cache-affinity auction...          [ok]',
  '',
  'Ready. Login to provision your embedded wallet.',
]

export function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [visibleLines, setVisibleLines] = useState(0)

  // Typewriter boot sequence — reveals one line at a time
  useEffect(() => {
    if (visibleLines >= BOOT_LINES.length) return
    const t = setTimeout(() => setVisibleLines(n => n + 1), 180)
    return () => clearTimeout(t)
  }, [visibleLines])

  const booted = visibleLines >= BOOT_LINES.length

  return (
    <div className="container" style={{ maxWidth: 640, paddingTop: 60 }}>
      {/* ASCII logo */}
      <pre style={{
        color: 'var(--green)',
        textShadow: 'var(--glow-green)',
        fontSize: 10,
        lineHeight: 1.1,
        marginBottom: 24,
        fontFamily: 'var(--font-mono)',
      }}>{`
 ██████   ██████  ██       ██   ██
██       ██    ██ ██       ██  ██
██   ███ ██    ██ ██       █████
██    ██ ██    ██ ██       ██  ██
 ██████   ██████  ███████  ██   ██
`}</pre>

      <h1 className="glow-in">surp</h1>
      <p className="sub">cheapest LLM inference on the internet — pay per request in USDC on Base</p>

      {/* Boot sequence */}
      <div className="card" style={{ minHeight: 200, marginBottom: 16 }}>
        {BOOT_LINES.slice(0, visibleLines).map((line, i) => (
          <div key={i} style={{
            color: line.includes('[ok]') ? 'var(--green)' : 'var(--text-dim)',
            fontSize: 12,
            lineHeight: 1.8,
          }}>
            {line.includes('[ok]') ? (
              <>{line.replace('[ok]', '')}<span style={{ color: 'var(--green)' }}>✓</span></>
            ) : line}
            {i === visibleLines - 1 && !booted && <span className="cursor-blink">▋</span>}
          </div>
        ))}
      </div>

      {/* Login */}
      <div className="card" style={{ opacity: booted ? 1 : 0.3, transition: 'opacity 0.5s' }}>
        <h2>━━ access terminal</h2>
        <p className="dim" style={{ marginBottom: 16 }}>
          Login with email, passkey, or Farcaster. An embedded wallet is created
          automatically on first login — use it to pay for inference with USDC on Base.
        </p>
        <button className="btn" onClick={onLogin} disabled={!booted} style={{ width: '100%' }}>
          ▶ login
        </button>
        <p className="faint" style={{ marginTop: 16, fontSize: 11 }}>
          non-custodial · only you control the keys · by logging in you agree to the surp terms
        </p>
      </div>

      <p className="faint" style={{ marginTop: 24, textAlign: 'center' }}>
        <a href="/">← back to surp.ivc.lol</a>
      </p>
    </div>
  )
}
