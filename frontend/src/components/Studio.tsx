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
const VIDEO_MODELS = [
  { id: 'fal-ai/minimax/video-01-live', label: 'MiniMax Video-01' },
  { id: 'fal-ai/kling-video/v2/master/image-to-video', label: 'Kling 2.0 Master' },
  { id: 'fal-ai/luma-dream-machine/image-to-video', label: 'Luma Dream Machine' },
]

export function Studio() {
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
            Set <code>SURP_FAL_KEY</code> in /etc/surp/surp.env to enable real Flux/Kling/MiniMax generation.
          </p>
        </div>
      )}
      {tab === 'chat' && <ChatPane authFetch={authFetch} />}
      {tab === 'image' && <ImagePane authFetch={authFetch} onDone={() => setTab('gallery')} />}
      {tab === 'video' && <VideoPane authFetch={authFetch} onDone={() => setTab('gallery')} />}
      {tab === 'gallery' && <Gallery authFetch={authFetch} />}
    </div>
  )
}

/* ── Chat ─────────────────────────────────────────────────────────────── */

function ChatPane({ authFetch }: { authFetch: (u: string, o?: any) => Promise<Response> }) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
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
        body: JSON.stringify({ messages: next.map(({ role, content }) => ({ role, content })) }),
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

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', minHeight: 480 }}>
      <p className="faint" style={{ margin: '0 0 8px', fontSize: 11 }}>▸ chat — treasury-sponsored surp/free · no wallet needed</p>
      <div style={{ flex: 1, overflowY: 'auto', maxHeight: 400, padding: 12, border: '1px solid var(--border)', borderRadius: 6, marginBottom: 12, background: 'rgba(0,0,0,0.3)' }}>
        {messages.length === 0 && <p className="dim" style={{ margin: 0 }}>ask anything — the model routes to the cheapest live chat model on Surplus.</p>}
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

function ImagePane({ authFetch, onDone }: { authFetch: (u: string, o?: any) => Promise<Response>; onDone: () => void }) {
  const [mode, setMode] = useState<'t2i' | 'i2i'>('t2i')
  const [prompt, setPrompt] = useState('')
  const [srcImage, setSrcImage] = useState<string>('')
  const [params, setParams] = useState<any>({ steps: 28, guidance: 3.5, seed: 0, strength: 0.6, aspect: 'square_hd' })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Creation | null>(null)
  const [err, setErr] = useState('')

  const upload = async (file: File) => {
    const fd = new FormData()
    fd.append('image', file)
    const res = await authFetch('/api/studio/upload', { method: 'POST', body: fd })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'upload failed')
    setSrcImage(data.url)
  }

  const generate = async () => {
    setBusy(true); setErr(''); setResult(null)
    try {
      const res = await authFetch('/api/studio/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: 'image', mode, prompt, image_url: srcImage, params }),
      })
      const data = await res.json()
      if (!res.ok) { setErr(data.error || 'generation failed'); return }
      setResult(data)
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
      <PromptBox prompt={prompt} setPrompt={setPrompt} preset="" onPreset={setPrompt}
        onGenerate={generate} busy={busy} label={mode === 't2i' ? 'generate image' : 'transform image'} />
      <ParamsPanel params={params} setParams={setParams} />
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

function VideoPane({ authFetch, onDone }: { authFetch: (u: string, o?: any) => Promise<Response>; onDone: () => void }) {
  const [mode, setMode] = useState<'t2v' | 'i2v'>('t2v')
  const [prompt, setPrompt] = useState('')
  const [srcImage, setSrcImage] = useState<string>('')
  const [videoModel, setVideoModel] = useState(VIDEO_MODELS[0].id)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Creation | null>(null)
  const [err, setErr] = useState('')

  const upload = async (file: File) => {
    const fd = new FormData(); fd.append('image', file)
    const res = await authFetch('/api/studio/upload', { method: 'POST', body: fd })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || 'upload failed')
    setSrcImage(data.url)
  }

  const generate = async () => {
    setBusy(true); setErr(''); setResult(null)
    try {
      const res = await authFetch('/api/studio/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: 'video', mode, prompt, image_url: srcImage, params: { video_model: videoModel } }),
      })
      const data = await res.json()
      if (!res.ok) { setErr(data.error || 'generation failed'); return }
      setResult(data)
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
