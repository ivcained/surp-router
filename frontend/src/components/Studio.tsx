import { useState, useEffect, useRef } from 'react'
import { useAuthFetch, fmtTime } from '../lib'

type StudioTab = 'chat' | 'image' | 'video' | 'gallery'
interface Msg { role: 'user' | 'assistant'; content: string }
interface Creation {
  id: number; kind: string; mode: string; prompt: string;
  media_url: string; thumb_url: string; is_public: boolean;
  share_token: string; created_at: number; provider?: string;
}

const PRESETS: { label: string; prompt: string }[] = [
  { label: 'photoreal', prompt: 'ultra-photorealistic, 8k, natural lighting, sharp focus' },
  { label: 'anime', prompt: 'anime style, studio ghibli inspired, vibrant colors, clean lineart' },
  { label: 'pixel art', prompt: 'pixel art, 16-bit retro game style, crisp pixels' },
  { label: 'cyberpunk', prompt: 'cyberpunk, neon lights, rainy night city, cinematic' },
  { label: 'watercolor', prompt: 'watercolor painting, soft washes, paper texture' },
  { label: '3d render', prompt: '3d render, octane, soft global illumination, depth of field' },
  { label: 'line art', prompt: 'minimal line art, single color on white, elegant' },
  { label: 'oil painting', prompt: 'oil painting, impasto brushstrokes, renaissance lighting' },
]

const ASPECTS = ['square_hd', 'portrait_4_3', 'landscape_4_3', 'portrait_16_9', 'landscape_16_9']

/* ── x402 payment helper ──────────────────────────────────────────────────
   The studio generate endpoint is x402-paywalled: the first call returns
   402 with a PAYMENT-REQUIRED header; the client signs an EIP-3009 USDC
   transfer (TransferWithAuthorization, EIP-712) with their wallet and
   retries with a PAYMENT-SIGNATURE header. Surp charges its router markup
   (5%) on top of the Surplus media-unit price. */
const USDC_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
const CHAIN_ID = 8453

function hexNonce(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return '0x' + Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('')
}

async function payAndRetry(
  authFetch: (u: string, o?: any) => Promise<Response>,
  wallet: { signTypedData: (d: any) => Promise<string>; address?: string } | undefined,
  body: any,
  paymentHeader: string,
): Promise<Response> {
  if (!wallet?.signTypedData) {
    throw new Error('wallet not connected — connect your wallet to pay for generation')
  }
  // Parse the PAYMENT-REQUIRED header (base64 JSON: {accepts: [{amount, payTo, ...}]})
  const decoded = JSON.parse(atob(paymentHeader))
  const req = decoded.accepts?.[0]
  if (!req) throw new Error('no payment requirements in header')

  const now = Math.floor(Date.now() / 1000)
  const nonce = hexNonce()
  const message = {
    from: wallet.address || '',
    to: req.payTo,
    value: BigInt(req.amount).toString(),
    validAfter: '0',
    validBefore: String(now + (req.maxTimeoutSeconds || 600)),
    nonce,
  }
  const domain = {
    name: 'USD Coin',
    version: '2',
    chainId: CHAIN_ID,
    verifyingContract: USDC_ADDRESS,
  }
  const types = {
    TransferWithAuthorization: [
      { name: 'from', type: 'address' },
      { name: 'to', type: 'address' },
      { name: 'value', type: 'uint256' },
      { name: 'validAfter', type: 'uint256' },
      { name: 'validBefore', type: 'uint256' },
      { name: 'nonce', type: 'bytes32' },
    ],
  }
  const signature = await wallet.signTypedData({ domain, types, primaryType: 'TransferWithAuthorization', message })

  // Build the x402 PaymentPayload (matches the gateway's expected schema).
  const payload = {
    x402Version: 2,
    payload: {
      authorization: {
        from: message.from,
        to: message.to,
        value: message.value,
        validAfter: message.validAfter,
        validBefore: message.validBefore,
        nonce: message.nonce,
      },
      signature,
    },
    accepted: [req],
    resource: {
      name: 'surp studio generation',
      mimeType: 'application/json',
      url: 'surp.ivc.lol/api/studio/generate',
    },
    extensions: {},
  }
  const header = btoa(JSON.stringify(payload))
  return authFetch('/api/studio/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'PAYMENT-SIGNATURE': header },
    body: JSON.stringify(body),
  })
}

const IMAGE_MODELS = [
  { id: 'venice-flux-1.1-pro', label: 'Flux 1.1 Pro' },
  { id: 'venice-flux-2-pro', label: 'Flux 2 Pro' },
  { id: 'venice-gpt-image-2', label: 'GPT Image 2' },
  { id: 'venice-hunyuan-image-v3', label: 'Hunyuan Image v3' },
  { id: 'venice-qwen-image-2', label: 'Qwen Image 2' },
  { id: 'venice-sd35', label: 'SD 3.5' },
  { id: 'venice-sdxl', label: 'SDXL' },
  { id: 'venice-z-image-turbo', label: 'Z-Image Turbo' },
]
const VIDEO_MODELS = [
  { id: 'venice-wan-2.7', label: 'Wan 2.7' },
  { id: 'venice-wan-2.7-pro', label: 'Wan 2.7 Pro' },
  { id: 'veo3-fast-text-to-video', label: 'Veo 3 Fast' },
  { id: 'seedance-1-5-pro-text-to-video', label: 'Seedance 1.5 Pro' },
  { id: 'kling-v3-pro-text-to-video', label: 'Kling v3 Pro' },
  { id: 'runway-gen4-turbo', label: 'Runway Gen4 Turbo' },
  { id: 'pixverse-v5-6-text-to-video', label: 'Pixverse v5.6' },
  { id: 'ltx-2-fast-text-to-video', label: 'LTX-2 Fast' },
]

export function Studio({ wallet }: { wallet?: { signTypedData: (d: any) => Promise<string>; address?: string } }) {
  const authFetch = useAuthFetch()
  const [tab, setTab] = useState<StudioTab>('chat')
  const [provider, setProvider] = useState<{ configured: boolean; provider: string } | null>(null)

  useEffect(() => {
    authFetch('/api/studio/status').then(r => r.json()).then(setProvider).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const tabStyle = (t: StudioTab): React.CSSProperties => ({
    padding: '8px 16px', background: tab === t ? 'rgba(0,255,156,0.08)' : 'transparent',
    border: '1px solid', borderColor: tab === t ? 'var(--green)' : 'var(--border)',
    color: tab === t ? 'var(--green)' : 'var(--text-dim)', borderRadius: 6, cursor: 'pointer',
    fontFamily: 'var(--font-mono)', fontSize: 13, textShadow: tab === t ? 'var(--glow-green)' : 'none',
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
        <h2 style={{ margin: 0, marginRight: 'auto' }}>studio</h2>
        <button style={tabStyle('chat')} onClick={() => setTab('chat')}>chat</button>
        <button style={tabStyle('image')} onClick={() => setTab('image')}>image</button>
        <button style={tabStyle('video')} onClick={() => setTab('video')}>video</button>
        <button style={tabStyle('gallery')} onClick={() => setTab('gallery')}>gallery</button>
      </div>
      {provider && !provider.configured && (
        <div className="card" style={{ borderColor: '#ffd23f', marginBottom: 16 }}>
          <p style={{ color: '#ffd23f', margin: 0 }}>
            ⚠ generation provider not configured — running in <b>mock mode</b>.
            Set <code>SURPLUS_INTELLIGENCE_API_KEY</code> in /etc/surp/surp.env to enable real Flux/Wan/Kling/Veo generation.
          </p>
        </div>
      )}
      {tab === 'chat' && <ChatPane authFetch={authFetch} />}
      {tab === 'image' && <ImagePane authFetch={authFetch} wallet={wallet} onDone={() => setTab('gallery')} />}
      {tab === 'video' && <VideoPane authFetch={authFetch} wallet={wallet} onDone={() => setTab('gallery')} />}
      {tab === 'gallery' && <Gallery authFetch={authFetch} />}
    </div>
  )
}

/* ── Chat ─────────────────────────────────────────────────────────────── */

const CHAT_MODELS = [
  { id: 'surp/free', label: 'surp/free', desc: 'best chat · general' },
  { id: 'surp/free-coding', label: 'surp/free-coding', desc: 'coder class · elevated budget' },
  { id: 'surp/free-fast', label: 'surp/free-fast', desc: 'mini/nano/lite · fastest' },
]

function ChatPane({ authFetch }: { authFetch: (u: string, o?: any) => Promise<Response> }) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [model, setModel] = useState(CHAT_MODELS[0].id)
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    const next: Msg[] = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setInput('')
    setBusy(true)
    try {
      const res = await authFetch('/api/studio/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next.map(({ role, content }) => ({ role, content })), model }),
      })
      const data = await res.json()
      const reply = data?.choices?.[0]?.message?.content ?? data?.error ?? 'no response'
      setMessages([...next, { role: 'assistant', content: reply }])
    } catch (e) {
      setMessages([...next, { role: 'assistant', content: `error: ${String(e)}` }])
    } finally {
      setBusy(false)
    }
  }

  const selected = CHAT_MODELS.find(m => m.id === model) || CHAT_MODELS[0]

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', minHeight: 480 }}>
      {/* Model picker — click-to-open dropdown (Open-Generative-AI style) */}
      <div style={{ position: 'relative', marginBottom: 10 }}>
        <button
          onClick={() => setOpen(!open)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, width: '100%',
            background: 'rgba(0,255,156,0.04)', border: '1px solid var(--border)',
            color: 'var(--fg)', borderRadius: 6, padding: '8px 12px', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 13, textAlign: 'left',
          }}
        >
          <span style={{ color: 'var(--green)' }}>▣</span>
          <span style={{ fontWeight: 700, color: 'var(--green)' }}>{selected.label}</span>
          <span className="dim" style={{ fontSize: 11, flex: 1 }}>{selected.desc}</span>
          <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>{open ? '▲' : '▼'}</span>
        </button>
        {open && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
            background: '#0a0f0b', border: '1px solid var(--border-bright)',
            borderRadius: 6, marginTop: 4, overflow: 'hidden', boxShadow: '0 8px 30px rgba(0,0,0,0.6)',
          }}>
            {CHAT_MODELS.map(m => (
              <button
                key={m.id}
                onClick={() => { setModel(m.id); setOpen(false) }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
                  background: m.id === model ? 'rgba(0,255,156,0.08)' : 'transparent',
                  border: 'none', borderBottom: '1px solid var(--border)',
                  color: 'var(--fg)', padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 13,
                }}
              >
                <span style={{ color: m.id === model ? 'var(--green)' : 'var(--fg)' }}>{m.label}</span>
                {m.id === model && <span style={{ color: 'var(--green)', marginLeft: 8 }}>●</span>}
                <span className="dim" style={{ display: 'block', fontSize: 11, marginTop: 2 }}>{m.desc}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="faint" style={{ margin: '0 0 8px', fontSize: 11 }}>▸ chat — treasury-sponsored · no wallet needed</p>
      <div style={{ flex: 1, overflowY: 'auto', maxHeight: 360, padding: 12, border: '1px solid var(--border)', borderRadius: 6, marginBottom: 12, background: 'rgba(0,0,0,0.3)' }}>
        {messages.length === 0 && (
          <button
            onClick={() => inputRef.current?.focus()}
            style={{
              background: 'transparent', border: 'none', color: 'var(--text-dim)', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 13, padding: 0, textAlign: 'left',
            }}
          >
            <span className="dim">ask anything — the model routes to the cheapest live chat model on Surplus.</span>
            <span style={{ color: 'var(--green)' }}> ▸ click to type</span>
          </button>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 10 }}>
            <span style={{ color: m.role === 'user' ? 'var(--cyan)' : 'var(--green)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {m.role === 'user' ? '❯ you' : '❯ surp'}
            </span>
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, marginTop: 2 }}>{m.content}</div>
          </div>
        ))}
        {busy && <p className="dim" style={{ fontFamily: 'var(--font-mono)' }}>▋ thinking...</p>}
        <div ref={endRef} />
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          ref={inputRef}
          value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') send() }}
          placeholder="type a message…"
          style={{ flex: 1, background: '#000', border: '1px solid var(--border)', color: 'var(--fg)', padding: '10px 12px', borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 14 }}
        />
        <button className="btn" onClick={send} disabled={busy}>{busy ? '…' : 'send'}</button>
      </div>
    </div>
  )
}

/* ── shared prompt + params ───────────────────────────────────────────── */

function ParamsPanel({ params, setParams }: { params: any; setParams: (p: any) => void }) {
  const row: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }
  const lbl: React.CSSProperties = { width: 110, color: 'var(--text-dim)', fontSize: 12, fontFamily: 'var(--font-mono)' }
  const inp: React.CSSProperties = { flex: 1, background: '#000', border: '1px solid var(--border)', color: 'var(--fg)', padding: '6px 8px', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 12 }
  const set = (k: string, v: any) => setParams({ ...params, [k]: v })
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <p className="faint" style={{ margin: '0 0 8px', fontSize: 11 }}>▸ advanced (comfy-style)</p>
      <div style={row}><span style={lbl}>steps</span><input type="number" style={inp} value={params.steps ?? 28} onChange={e => set('steps', +e.target.value)} /></div>
      <div style={row}><span style={lbl}>guidance</span><input type="number" step="0.5" style={inp} value={params.guidance ?? 3.5} onChange={e => set('guidance', +e.target.value)} /></div>
      <div style={row}><span style={lbl}>seed</span><input type="number" style={inp} value={params.seed ?? 0} onChange={e => set('seed', +e.target.value)} /><button className="btn btn-outline" onClick={() => set('seed', 0)}>random</button></div>
      <div style={row}><span style={lbl}>strength</span><input type="number" step="0.05" min="0" max="1" style={inp} value={params.strength ?? 0.6} onChange={e => set('strength', +e.target.value)} /></div>
    </div>
  )
}

function PromptBox({ prompt, setPrompt, preset, onPreset, onGenerate, busy, label }: {
  prompt: string; setPrompt: (s: string) => void; preset: string;
  onPreset: (s: string) => void; onGenerate: () => void; busy: boolean; label: string
}) {
  return (
    <>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        {PRESETS.map(p => (
          <button key={p.label} className="btn btn-outline" style={{ padding: '4px 10px', fontSize: 12 }}
            onClick={() => onPreset(prompt ? `${prompt}, ${p.prompt}` : p.prompt)}>
            + {p.label}
          </button>
        ))}
      </div>
      <textarea
        value={prompt} onChange={e => setPrompt(e.target.value)}
        placeholder={`describe what to generate…`}
        rows={3}
        style={{ width: '100%', background: '#000', border: '1px solid var(--border)', color: 'var(--fg)', padding: 10, borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 14, resize: 'vertical' }}
      />
      <div style={{ marginTop: 8 }}>
        <button className="btn" onClick={onGenerate} disabled={busy || !prompt.trim()}>
          {busy ? 'generating…' : `▶ ${label}`}
        </button>
      </div>
    </>
  )
}

/* ── Image ────────────────────────────────────────────────────────────── */

function ImagePane({ authFetch, wallet, onDone }: {
  authFetch: (u: string, o?: any) => Promise<Response>
  wallet?: { signTypedData: (d: any) => Promise<string>; address?: string }
  onDone: () => void
}) {
  const [mode, setMode] = useState<'t2i' | 'i2i'>('t2i')
  const [prompt, setPrompt] = useState('')
  const [srcImage, setSrcImage] = useState<string>('')
  const [imageModel, setImageModel] = useState(IMAGE_MODELS[0].id)
  const [params, setParams] = useState<any>({ steps: 28, guidance: 3.5, seed: 0, strength: 0.6, aspect: 'square_hd' })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Creation | null>(null)
  const [err, setErr] = useState('')
  const [quote, setQuote] = useState<{ price_usd: string; model: string } | null>(null)

  const upload = async (file: File) => {
    const fd = new FormData()
    fd.append('image', file)
    const res = await authFetch('/api/studio/upload', { method: 'POST', body: fd })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'upload failed')
    setSrcImage(data.url)
  }

  const generate = async () => {
    setBusy(true); setErr(''); setResult(null); setQuote(null)
    const body = { kind: 'image', mode, prompt, image_url: srcImage, params: { ...params, image_model: imageModel } }
    try {
      // Phase 1: get the quote (402 + PAYMENT-REQUIRED header)
      const res1 = await authFetch('/api/studio/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data1 = await res1.json()
      if (res1.status === 402 && data1?.error === 'payment-required') {
        const payHeader = res1.headers.get('PAYMENT-REQUIRED') || ''
        if (!payHeader) { setErr(data1.error || 'payment required but no header'); setBusy(false); return }
        // Show the quote and require the wallet to sign
        setQuote({ price_usd: data1.price_usd || '?', model: data1.model || imageModel })
        if (!wallet?.signTypedData) {
          setErr('connect your wallet to pay for generation')
          setBusy(false)
          return
        }
        const res2 = await payAndRetry(authFetch, wallet, body, payHeader)
        const data2 = await res2.json()
        if (!res2.ok) {
          setErr(data2.error || 'payment or generation failed')
          setBusy(false)
          return
        }
        setResult(data2)
        onDone()
        setBusy(false)
        return
      }
      if (!res1.ok) {
        if (res1.status === 402) {
          setErr(`⚠ ${data1.error || 'insufficient balance'} — add USDC to your wallet first.`)
        } else {
          setErr(data1.error || 'generation failed')
        }
        setBusy(false)
        return
      }
      setResult(data1)
      onDone()
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button className="btn btn-outline" style={{ background: mode === 't2i' ? 'rgba(0,255,156,0.08)' : 'transparent' }} onClick={() => setMode('t2i')}>text → image</button>
        <button className="btn btn-outline" style={{ background: mode === 'i2i' ? 'rgba(0,255,156,0.08)' : 'transparent' }} onClick={() => setMode('i2i')}>image → image</button>
      </div>
      {mode === 'i2i' && (
        <div style={{ marginBottom: 12 }}>
          {srcImage ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <img src={srcImage} alt="" style={{ width: 96, height: 96, objectFit: 'cover', borderRadius: 6, border: '1px solid var(--border)' }} />
              <button className="btn btn-outline" onClick={() => setSrcImage('')}>remove</button>
            </div>
          ) : (
            <label className="btn btn-outline" style={{ cursor: 'pointer', display: 'inline-block' }}>
              ⬆ upload source image
              <input type="file" accept="image/*" hidden onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
          )}
        </div>
      )}
      <div style={{ marginBottom: 12 }}>
        <span className="dim" style={{ fontSize: 12, marginRight: 8 }}>model:</span>
        <select value={imageModel} onChange={e => setImageModel(e.target.value)}
          style={{ background: '#000', color: 'var(--fg)', border: '1px solid var(--border)', borderRadius: 4, padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {IMAGE_MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
      </div>
      <PromptBox prompt={prompt} setPrompt={setPrompt} preset="" onPreset={setPrompt}
        onGenerate={generate} busy={busy} label={mode === 't2i' ? 'generate image' : 'transform image'} />
      <ParamsPanel params={params} setParams={setParams} />
      {quote && !busy && (
        <p className="dim" style={{ marginTop: 10, fontSize: 12 }}>
          ▸ {quote.model} · <b style={{ color: 'var(--green)' }}>{quote.price_usd}</b> (surplus + 5% router) — sign the payment in your wallet
        </p>
      )}
      {err && <p style={{ color: 'var(--red)', marginTop: 10 }}>{err}</p>}
      {result && (
        <div style={{ marginTop: 12 }}>
          <img src={result.media_url} alt="" style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid var(--border)' }} />
          <p className="dim" style={{ fontSize: 11 }}>saved to gallery · provider: {result.provider}</p>
        </div>
      )}
    </div>
  )
}

/* ── Video ────────────────────────────────────────────────────────────── */

function VideoPane({ authFetch, wallet, onDone }: {
  authFetch: (u: string, o?: any) => Promise<Response>
  wallet?: { signTypedData: (d: any) => Promise<string>; address?: string }
  onDone: () => void
}) {
  const [mode, setMode] = useState<'t2v' | 'i2v'>('t2v')
  const [prompt, setPrompt] = useState('')
  const [srcImage, setSrcImage] = useState<string>('')
  const [videoModel, setVideoModel] = useState(VIDEO_MODELS[0].id)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Creation | null>(null)
  const [err, setErr] = useState('')
  const [quote, setQuote] = useState<{ price_usd: string; model: string } | null>(null)

  const upload = async (file: File) => {
    const fd = new FormData(); fd.append('image', file)
    const res = await authFetch('/api/studio/upload', { method: 'POST', body: fd })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'upload failed')
    setSrcImage(data.url)
  }

  const generate = async () => {
    setBusy(true); setErr(''); setResult(null); setQuote(null)
    const body = { kind: 'video', mode, prompt, image_url: srcImage, params: { video_model: videoModel } }
    try {
      const res1 = await authFetch('/api/studio/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data1 = await res1.json()
      if (res1.status === 402 && data1?.error === 'payment-required') {
        const payHeader = res1.headers.get('PAYMENT-REQUIRED') || ''
        if (!payHeader) { setErr(data1.error || 'payment required but no header'); setBusy(false); return }
        setQuote({ price_usd: data1.price_usd || '?', model: data1.model || videoModel })
        if (!wallet?.signTypedData) {
          setErr('connect your wallet to pay for generation')
          setBusy(false)
          return
        }
        const res2 = await payAndRetry(authFetch, wallet, body, payHeader)
        const data2 = await res2.json()
        if (!res2.ok) { setErr(data2.error || 'payment or generation failed'); setBusy(false); return }
        setResult(data2)
        onDone()
        setBusy(false)
        return
      }
      if (!res1.ok) {
        if (res1.status === 402) {
          setErr(`⚠ ${data1.error || 'insufficient balance'} — add USDC to your wallet first.`)
        } else {
          setErr(data1.error || 'generation failed')
        }
        setBusy(false)
        return
      }
      setResult(data1)
      onDone()
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button className="btn btn-outline" style={{ background: mode === 't2v' ? 'rgba(0,255,156,0.08)' : 'transparent' }} onClick={() => setMode('t2v')}>text → video</button>
        <button className="btn btn-outline" style={{ background: mode === 'i2v' ? 'rgba(0,255,156,0.08)' : 'transparent' }} onClick={() => setMode('i2v')}>image → video</button>
      </div>
      {mode === 'i2v' && (
        <div style={{ marginBottom: 12 }}>
          {srcImage ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <img src={srcImage} alt="" style={{ width: 96, height: 96, objectFit: 'cover', borderRadius: 6, border: '1px solid var(--border)' }} />
              <button className="btn btn-outline" onClick={() => setSrcImage('')}>remove</button>
            </div>
          ) : (
            <label className="btn btn-outline" style={{ cursor: 'pointer', display: 'inline-block' }}>
              ⬆ upload start frame
              <input type="file" accept="image/*" hidden onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
          )}
        </div>
      )}
      <div style={{ marginBottom: 12 }}>
        <span className="dim" style={{ fontSize: 12, marginRight: 8 }}>model:</span>
        <select value={videoModel} onChange={e => setVideoModel(e.target.value)}
          style={{ background: '#000', color: 'var(--fg)', border: '1px solid var(--border)', borderRadius: 4, padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {VIDEO_MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
      </div>
      <PromptBox prompt={prompt} setPrompt={setPrompt} preset="" onPreset={setPrompt}
        onGenerate={generate} busy={busy} label={mode === 't2v' ? 'generate video' : 'animate image'} />
      {quote && !busy && (
        <p className="dim" style={{ marginTop: 10, fontSize: 12 }}>
          ▸ {quote.model} · <b style={{ color: 'var(--green)' }}>{quote.price_usd}</b> (surplus + 5% router) — sign the payment in your wallet
        </p>
      )}
      {err && <p style={{ color: 'var(--red)', marginTop: 10 }}>{err}</p>}
      {result && (
        <div style={{ marginTop: 12 }}>
          {result.media_url.endsWith('.svg') || result.media_url.endsWith('.png') || result.media_url.endsWith('.jpg') ? (
            <img src={result.media_url} alt="" style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid var(--border)' }} />
          ) : (
            <video src={result.media_url} controls style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid var(--border)' }} />
          )}
          <p className="dim" style={{ fontSize: 11 }}>saved to gallery · provider: {result.provider}</p>
        </div>
      )}
    </div>
  )
}

/* ── Gallery ──────────────────────────────────────────────────────────── */

function Gallery({ authFetch }: { authFetch: (u: string, o?: any) => Promise<Response> }) {
  const [creations, setCreations] = useState<Creation[]>([])
  const [loaded, setLoaded] = useState(false)

  const load = async () => {
    try {
      const res = await authFetch('/api/studio/creations')
      const data = await res.json()
      setCreations(data.creations || [])
    } catch (e) { /* ignore */ }
    setLoaded(true)
  }
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleShare = async (c: Creation) => {
    const res = await authFetch(`/api/studio/share/${c.id}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_public: !c.is_public }),
    })
    if (res.ok) {
      const updated = await res.json()
      setCreations(creations.map(x => x.id === updated.id ? { ...x, is_public: updated.is_public, share_token: updated.share_token } : x))
    }
  }

  const del = async (c: Creation) => {
    await authFetch(`/api/studio/creations/${c.id}`, { method: 'DELETE' })
    setCreations(creations.filter(x => x.id !== c.id))
  }

  if (!loaded) return <div className="card"><p className="dim">loading gallery…</p></div>
  if (creations.length === 0) return <div className="card"><p className="dim">no creations yet — generate something in the image or video tabs.</p></div>

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
      {creations.map(c => {
        const isImg = c.media_url.endsWith('.svg') || c.media_url.endsWith('.png') || c.media_url.endsWith('.jpg')
        return (
          <div key={c.id} className="card" style={{ padding: 10 }}>
            {isImg ? (
              <img src={c.media_url} alt="" style={{ width: '100%', aspectRatio: '1/1', objectFit: 'cover', borderRadius: 6, border: '1px solid var(--border)' }} />
            ) : (
              <video src={c.media_url} muted style={{ width: '100%', aspectRatio: '1/1', objectFit: 'cover', borderRadius: 6, border: '1px solid var(--border)' }} />
            )}
            <p className="faint" style={{ fontSize: 10, margin: '8px 0 4px' }}>{c.mode.toUpperCase()} · {fmtTime(c.created_at)}</p>
            <p style={{ fontSize: 12, margin: '0 0 8px', maxHeight: 40, overflow: 'hidden' }}>{c.prompt}</p>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn btn-outline" style={{ padding: '4px 8px', fontSize: 11 }} onClick={() => toggleShare(c)}>
                {c.is_public ? '🔓 public' : '🔒 private'}
              </button>
              {c.is_public && c.share_token && (
                <a className="btn btn-outline" style={{ padding: '4px 8px', fontSize: 11, textDecoration: 'none' }}
                   href={`/studio/share/${c.share_token}`} target="_blank" rel="noopener">share ↗</a>
              )}
              <button className="btn btn-outline" style={{ padding: '4px 8px', fontSize: 11, color: 'var(--red)' }} onClick={() => del(c)}>✕</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
