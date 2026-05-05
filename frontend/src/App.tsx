import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'

function renderPostText(text: string) {
  // Convert **bold**, *italic*, and newlines to JSX
  const lines = text.split('\n')
  return lines.map((line, i) => {
    const parts: React.ReactNode[] = []
    const re = /(\*\*(.+?)\*\*|\*(.+?)\*)/g
    let last = 0, m: RegExpExecArray | null
    while ((m = re.exec(line)) !== null) {
      if (m.index > last) parts.push(line.slice(last, m.index))
      if (m[2]) parts.push(<strong key={m.index}>{m[2]}</strong>)
      else if (m[3]) parts.push(<em key={m.index}>{m[3]}</em>)
      last = m.index + m[0].length
    }
    if (last < line.length) parts.push(line.slice(last))
    return <span key={i}>{parts}{i < lines.length - 1 ? <br /> : null}</span>
  })
}

type Platform = 'linkedin' | 'instagram'

type JobStatus = 'queued' | 'running' | 'done' | 'error'

type GeneratePostResponse = {
  retrieval_pack: unknown
  content_draft: any
  final_output: any
}

type JobStatusResponse = {
  job_id: string
  status: JobStatus
  error?: string | null
  result?: any
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

const DEFAULT_AVATAR_DESCRIPTION = `Subject: Young East Asian woman, approximately 20–28 years old, with a natural and approachable appearance.
Face shape and structure: Oval-to-round face with soft, balanced proportions. High cheekbones, a smooth forehead, and a gently defined jawline with a soft chin.
Eyes: Almond-shaped dark brown eyes with a slight upward tilt at the outer corners. Natural, well-groomed eyebrows that are moderately thick, arched gently, and dark brown matching the hair.
Nose: Small, straight nose with a softly rounded tip and subtle, refined nostrils.
Lips: Full lips with a defined Cupid's bow. Warm rose-nude color, slightly glossy. Relaxed, gentle closed-mouth smile that creates very subtle dimpling at the corners.
Skin: Smooth, even-toned light warm complexion with a healthy luminous finish. Minimal visible pores. Light, natural-looking makeup: subtle eyeliner on upper lids, light mascara, and soft rose-nude lip color.
Hair: Dark brown to near-black, thick, shoulder-length with loose soft waves. Side-parted (left side), with the hair flowing naturally behind the shoulders. Healthy shine with volume at the crown.
Clothing: Light blue denim jacket (slightly distressed wash) worn open over a plain white crew-neck t-shirt. Casual, everyday style.
Expression and posture: Calm, friendly, and confident. Slight forward-facing posture, looking directly at the viewer with a subtle soft smile.`

function b64ToBlobUrl(b64: string, mime: string) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  const blob = new Blob([bytes], { type: mime })
  return URL.createObjectURL(blob)
}

type CanonicalAvatar = { description: string; imageBase64: string; mimeType: string }

function App() {
  const [activeTab, setActiveTab] = useState<'generate' | 'avatar'>('generate')

  // Avatar tab state
  const [canonicalAvatar, setCanonicalAvatar] = useState<CanonicalAvatar | null>(null)
  const [avatarDescription, setAvatarDescription] = useState(DEFAULT_AVATAR_DESCRIPTION)
  const [avatarImageBase64, setAvatarImageBase64] = useState('')
  const [avatarMimeType, setAvatarMimeType] = useState('image/png')
  const [avatarGenerating, setAvatarGenerating] = useState(false)
  const [avatarSaving, setAvatarSaving] = useState(false)
  const [avatarError, setAvatarError] = useState<string | null>(null)

  const [topics, setTopics] = useState<string[]>([])
  const [topic, setTopic] = useState<string>('')
  const [platform, setPlatform] = useState<Platform>('linkedin')

  function loadSaved<T>(key: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(key)
      return raw ? (JSON.parse(raw) as T) : fallback
    } catch { return fallback }
  }

  const [phase, setPhase] = useState<'idle' | 'post_running' | 'post_done' | 'video_running' | 'video_done'>(
    () => {
      const saved = loadSaved<string>('phase', 'idle')
      // Only restore terminal phases — never restore mid-run states
      return (saved === 'post_done' || saved === 'video_done') ? saved as any : 'idle'
    }
  )

  const [retrievalPack, setRetrievalPack] = useState<any>(() => loadSaved('retrievalPack', null))
  const [contentDraft, setContentDraft] = useState<any>(() => loadSaved('contentDraft', null))
  const [finalOutput, setFinalOutput] = useState<any>(() => loadSaved('finalOutput', null))

  const [imageGenerating, setImageGenerating] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [videoOutput, setVideoOutput] = useState<any>(() => loadSaved('videoOutput', null))
  const [qcResult, setQcResult] = useState<any>(() => loadSaved('qcResult', null))
  const [error, setError] = useState<string | null>(null)

  function safeSave(key: string, value: any, strip?: string[]) {
    try {
      const obj = strip ? Object.fromEntries(Object.entries(value ?? {}).filter(([k]) => !strip.includes(k))) : value
      localStorage.setItem(key, JSON.stringify(obj))
    } catch { /* quota exceeded — skip silently */ }
  }

  // Persist key state to localStorage whenever it changes
  useEffect(() => { if (phase === 'post_done' || phase === 'video_done') safeSave('phase', phase) }, [phase])
  useEffect(() => { if (retrievalPack) safeSave('retrievalPack', retrievalPack) }, [retrievalPack])
  useEffect(() => { if (contentDraft) safeSave('contentDraft', contentDraft) }, [contentDraft])
  useEffect(() => { if (finalOutput) safeSave('finalOutput', finalOutput) }, [finalOutput])
  useEffect(() => { if (videoOutput) safeSave('videoOutput', videoOutput, ['video_b64', 'thumbnail_b64']) }, [videoOutput])
  useEffect(() => { if (qcResult) safeSave('qcResult', qcResult) }, [qcResult])

  // storyboard edits
  const storyboard = contentDraft?.video_brief?.storyboard ?? []
  const [editedStoryboard, setEditedStoryboard] = useState<any[] | null>(null)
  const [editedSsml, setEditedSsml] = useState<string>('')

  useEffect(() => {
    ;(async () => {
      const res = await fetch(`${API_BASE}/topics`)
      const json = await res.json()
      setTopics(json.topics ?? [])
      setTopic((json.topics?.[0] as string) ?? '')
    })().catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    ;(async () => {
      const res = await fetch(`${API_BASE}/avatar`)
      const json = await res.json()
      if (json.image_base64) {
        setCanonicalAvatar({ description: json.description, imageBase64: json.image_base64, mimeType: json.mime_type ?? 'image/png' })
        setAvatarDescription(json.description || DEFAULT_AVATAR_DESCRIPTION)
        setAvatarImageBase64(json.image_base64)
        setAvatarMimeType(json.mime_type ?? 'image/png')
      }
    })().catch(() => {/* non-critical */})
  }, [])

  useEffect(() => {
    // reset local edits when new draft arrives
    if (contentDraft?.video_brief?.storyboard) {
      setEditedStoryboard(contentDraft.video_brief.storyboard)
      setEditedSsml(contentDraft.video_brief.ssml_script ?? '')
    }
  }, [contentDraft])

  const postImageUrl = useMemo(() => {
    const b64 = finalOutput?.image_b64
    if (!b64) return null
    const mime = finalOutput?.image_mime ?? (b64.startsWith("iVBORw") ? "image/png" : "image/jpeg")
    return b64ToBlobUrl(b64, mime)
  }, [finalOutput])

  const videoUrl = useMemo(() => {
    const b64 = videoOutput?.video_b64
    if (!b64) return null
    return b64ToBlobUrl(b64, 'video/mp4')
  }, [videoOutput])

  const onGenerateAvatarImage = useCallback(async () => {
    setAvatarError(null)
    setAvatarGenerating(true)
    try {
      const res = await fetch(`${API_BASE}/avatar/generate-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: avatarDescription }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        throw new Error(j?.detail ?? `HTTP ${res.status}`)
      }
      const json = await res.json()
      setAvatarImageBase64(json.image_base64)
      setAvatarMimeType(json.mime_type ?? 'image/png')
    } catch (e) {
      setAvatarError(String(e))
    } finally {
      setAvatarGenerating(false)
    }
  }, [avatarDescription])

  const onSaveAvatar = useCallback(async () => {
    setAvatarError(null)
    setAvatarSaving(true)
    try {
      const res = await fetch(`${API_BASE}/avatar/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: avatarDescription, image_base64: avatarImageBase64, mime_type: avatarMimeType }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        throw new Error(j?.detail ?? `HTTP ${res.status}`)
      }
      setCanonicalAvatar({ description: avatarDescription, imageBase64: avatarImageBase64, mimeType: avatarMimeType })
    } catch (e) {
      setAvatarError(String(e))
    } finally {
      setAvatarSaving(false)
    }
  }, [avatarDescription, avatarImageBase64, avatarMimeType])

  async function onRegenerateImage() {
    if (!contentDraft) return
    setImageGenerating(true)
    try {
      const res = await fetch(`${API_BASE}/generate/image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_prompt: contentDraft.image_prompt ?? contentDraft.topic ?? '',
          avatar_description: contentDraft.video_brief?.avatar_description ?? '',
        }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        throw new Error(j?.detail ?? `HTTP ${res.status}`)
      }
      const json = await res.json()
      setFinalOutput((prev: any) => ({ ...prev, image_b64: json.image_b64 }))
    } catch (e) {
      setError(String(e))
    } finally {
      setImageGenerating(false)
    }
  }

  async function onGeneratePost() {
    setError(null)
    setPhase('post_running')
    setRetrievalPack(null)
    setContentDraft(null)
    setFinalOutput(null)
    setVideoOutput(null)
    setQcResult(null)
    setJobId(null)
    setJobStatus(null)

    const res = await fetch(`${API_BASE}/generate/post`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic,
        platform,
        canonical_avatar: canonicalAvatar
          ? { description: canonicalAvatar.description, image_base64: canonicalAvatar.imageBase64, mime_type: canonicalAvatar.mimeType }
          : null,
      }),
    })
    if (!res.ok) {
      let detail = ''
      try {
        const j = await res.json()
        detail = typeof j?.detail === 'string' ? ` — ${j.detail}` : ''
      } catch {
        // ignore JSON parse errors
      }
      throw new Error(`generate/post failed: ${res.status}${detail}`)
    }
    const json = (await res.json()) as GeneratePostResponse
    setRetrievalPack(json.retrieval_pack)
    setContentDraft(json.content_draft)
    setFinalOutput(json.final_output)
    setPhase('post_done')
  }

  async function onGenerateVideo() {
    if (!contentDraft || !finalOutput) return
    setError(null)
    setPhase('video_running')

    const patchedDraft = { ...contentDraft }
    if (patchedDraft.video_brief) {
      patchedDraft.video_brief = { ...patchedDraft.video_brief }
      if (editedStoryboard) patchedDraft.video_brief.storyboard = editedStoryboard
      if (editedSsml) patchedDraft.video_brief.ssml_script = editedSsml
    }

    const res = await fetch(`${API_BASE}/generate/video_async`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_draft: patchedDraft, final_output: finalOutput }),
    })
    if (!res.ok) {
      throw new Error(`generate/video_async failed: ${res.status}`)
    }
    const json = await res.json()
    setJobId(json.job_id)
    setJobStatus('queued')
  }

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`)
        const json = (await res.json()) as JobStatusResponse
        if (cancelled) return
        setJobStatus(json.status)
        if (json.status === 'done') {
          setVideoOutput(json.result?.video_output ?? null)
          setQcResult(json.result?.qc_result ?? null)
          setPhase('video_done')
          clearInterval(interval)
        }
        if (json.status === 'error') {
          setError(json.error ?? 'video job failed')
          setPhase('post_done')
          clearInterval(interval)
        }
      } catch (e) {
        if (cancelled) return
        setError(String(e))
        setPhase('post_done')
        clearInterval(interval)
      }
    }, 2000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [jobId])

  function resetAll() {
    setError(null)
    setPhase('idle')
    setRetrievalPack(null)
    setContentDraft(null)
    setFinalOutput(null)
    setVideoOutput(null)
    setQcResult(null)
    setJobId(null)
    setJobStatus(null)
    setEditedStoryboard(null)
    setEditedSsml('')
    ;['phase', 'retrievalPack', 'contentDraft', 'finalOutput', 'videoOutput', 'qcResult'].forEach(
      (k) => localStorage.removeItem(k)
    )
  }

  return (
    <div className="page">
      <div className="container">
        <header className="topbar">
          <div>
            <h2 className="brandTitle">International Student AI Influencer</h2>
            <div className="brandTagline">Turn live sources into a post + storyboard + video.</div>
          </div>
          <button className="btn btnSecondary" onClick={resetAll}>
            Reset
          </button>
        </header>

        <nav className="tab-bar">
          <button
            className={`tab-btn${activeTab === 'generate' ? ' active' : ''}`}
            onClick={() => setActiveTab('generate')}
          >
            Generate
          </button>
          <button
            className={`tab-btn${activeTab === 'avatar' ? ' active' : ''}`}
            onClick={() => setActiveTab('avatar')}
          >
            Avatar {canonicalAvatar ? '✓' : ''}
          </button>
        </nav>

        {error ? (
          <div className="errorBox">
            <strong>Error:</strong> {error}
          </div>
        ) : null}

        {activeTab === 'avatar' ? (
        <section className="card">
          <h3 className="cardTitle">Avatar Editor</h3>
          {avatarError ? <div className="errorBox" style={{ marginBottom: 12 }}><strong>Error:</strong> {avatarError}</div> : null}
          <label>
            <span className="fieldLabel">Avatar description</span>
            <textarea
              className="textarea"
              rows={10}
              value={avatarDescription}
              onChange={(e) => setAvatarDescription(e.target.value)}
              style={{ marginTop: 6 }}
            />
          </label>
          <div style={{ marginTop: 12, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <button
              className="btn"
              onClick={() => void onGenerateAvatarImage()}
              disabled={!avatarDescription || avatarGenerating}
            >
              {avatarGenerating ? 'Generating…' : 'Generate Avatar Image'}
            </button>
            <button
              className="btn btnSecondary"
              onClick={() => void onSaveAvatar()}
              disabled={!avatarImageBase64 || avatarSaving}
            >
              {avatarSaving ? 'Saving…' : 'Save as Canonical Avatar'}
            </button>
          </div>
          {avatarImageBase64 ? (
            <img
              src={`data:${avatarMimeType};base64,${avatarImageBase64}`}
              alt="Avatar preview"
              className="avatar-preview"
            />
          ) : null}
          {canonicalAvatar ? (
            <div className="avatar-status-ok">Canonical avatar active — used for all videos and posts.</div>
          ) : (
            <div className="avatar-status-warn">No canonical avatar saved yet. Generate and save one above.</div>
          )}
        </section>
        ) : null}

        {activeTab === 'generate' ? (<>

        <section className="card">
          <h3 className="cardTitle">Generate Post + Storyboard</h3>
          <div className="grid2">
            <label>
              <span className="fieldLabel">Topic</span>
              <select className="select" value={topic} onChange={(e) => setTopic(e.target.value)}>
                {topics.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className="fieldLabel">Platform</span>
              <div className="pillRow">
                <div
                  className={`pill ${platform === 'linkedin' ? 'pillActive' : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setPlatform('linkedin')}
                  onKeyDown={(e) => (e.key === 'Enter' ? setPlatform('linkedin') : null)}
                >
                  <input type="radio" checked={platform === 'linkedin'} readOnly />
                  LinkedIn
                </div>
                <div
                  className={`pill ${platform === 'instagram' ? 'pillActive' : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setPlatform('instagram')}
                  onKeyDown={(e) => (e.key === 'Enter' ? setPlatform('instagram') : null)}
                >
                  <input type="radio" checked={platform === 'instagram'} readOnly />
                  Instagram
                </div>
              </div>
            </label>
          </div>

          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <button
              className="btn"
              onClick={() => void onGeneratePost().catch((e) => setError(String(e)))}
              disabled={!topic || phase === 'post_running' || phase === 'video_running'}
            >
              {phase === 'post_running' ? 'Generating…' : 'Generate Post + Storyboard'}
            </button>
            {phase === 'post_running' ? <span className="muted">Working… this can take ~30–90s.</span> : null}
            {phase === 'video_running' ? <span className="muted">Video job: {jobStatus ?? '...'}</span> : null}
          </div>
        </section>

      {phase !== 'idle' && finalOutput ? (
        <section className="card">
          <h3 className="cardTitle">Post Preview</h3>
          <div className="mediaGrid">
            <div>
              {postImageUrl ? (
                <img src={postImageUrl} alt="Generated" className="img" />
              ) : (
                <div className="details" style={{ textAlign: 'center', padding: 24 }}>
                  <div style={{ marginBottom: 12, opacity: 0.7 }}>No image</div>
                  <button
                    className="btn"
                    style={{ fontSize: 13 }}
                    disabled={imageGenerating}
                    onClick={() => void onRegenerateImage()}
                  >
                    {imageGenerating ? 'Generating…' : 'Generate Image'}
                  </button>
                </div>
              )}
            </div>
            <div>
              <div style={{ lineHeight: 1.6, fontSize: 14 }}>
                {renderPostText(finalOutput.body ?? finalOutput.caption ?? '(no post body)')}
              </div>
              {finalOutput.hashtags ? <div style={{ marginTop: 10, opacity: 0.9 }}>{finalOutput.hashtags}</div> : null}
            </div>
          </div>
        </section>
      ) : null}

      {phase !== 'idle' && contentDraft?.video_brief ? (
        <section className="card">
          <h3 className="cardTitle">Storyboard Editor</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, opacity: 0.9 }}>
            <div>
              <strong>Avatar:</strong> {String(contentDraft.video_brief.avatar_description ?? '').slice(0, 120)}
            </div>
            <div>
              <strong>Voice:</strong> Chirp3-HD · {contentDraft.video_brief.voice_gender ?? 'female'}
            </div>
            <div>
              <strong>Music mood:</strong> {contentDraft.video_brief.music_mood ?? ''}
            </div>
          </div>

          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
            {(editedStoryboard ?? storyboard).map((scene: any, idx: number) => (
              <details key={idx} open={idx === 0} className="details">
                <summary className="summary">
                  Scene {scene.scene ?? idx + 1} — {scene.camera_angle ?? ''} · {scene.emotion ?? ''}
                </summary>
                <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <label>
                    <span className="fieldLabel">Visual prompt (Veo / Imagen)</span>
                    <textarea
                      value={scene.visual_prompt ?? ''}
                      onChange={(e) => {
                        const next = [...(editedStoryboard ?? storyboard)]
                        next[idx] = { ...next[idx], visual_prompt: e.target.value }
                        setEditedStoryboard(next)
                      }}
                      rows={5}
                      className="textarea"
                    />
                  </label>
                  <label>
                    <span className="fieldLabel">Voiceover (spoken text)</span>
                    <textarea
                      value={scene.voiceover ?? ''}
                      onChange={(e) => {
                        const next = [...(editedStoryboard ?? storyboard)]
                        next[idx] = { ...next[idx], voiceover: e.target.value }
                        setEditedStoryboard(next)
                      }}
                      rows={5}
                      className="textarea"
                    />
                  </label>
                </div>

                <label style={{ display: 'block', marginTop: 10 }}>
                  <span className="fieldLabel">Duration (seconds)</span>
                  <input
                    type="number"
                    min={5}
                    max={12}
                    value={Number(scene.duration_seconds ?? 8)}
                    onChange={(e) => {
                      const next = [...(editedStoryboard ?? storyboard)]
                      next[idx] = { ...next[idx], duration_seconds: Number(e.target.value) }
                      setEditedStoryboard(next)
                    }}
                    className="input"
                    style={{ width: 120, marginLeft: 10 }}
                  />
                  <span style={{ marginLeft: 10, opacity: 0.8 }}>(Veo caps at 8s)</span>
                </label>
              </details>
            ))}
          </div>

          <details style={{ marginTop: 12 }} className="details">
            <summary className="summary">Full SSML script (editable)</summary>
            <textarea
              value={editedSsml}
              onChange={(e) => setEditedSsml(e.target.value)}
              rows={10}
              className="textarea"
              style={{ marginTop: 10 }}
            />
          </details>

          <div style={{ marginTop: 12 }}>
            <button
              className="btn"
              onClick={() => void onGenerateVideo().catch((e) => setError(String(e)))}
              disabled={phase !== 'post_done'}
            >
              Generate AI Influencer Video
            </button>
            {phase === 'video_running' ? <span style={{ marginLeft: 10 }}>Job: {jobStatus ?? '...'}</span> : null}
          </div>
        </section>
      ) : null}

      {phase === 'video_done' ? (
        <section className="card">
          <h3 className="cardTitle">AI Influencer Video</h3>
          {videoUrl ? (
            <video src={videoUrl} controls style={{ width: '100%', borderRadius: 16 }} />
          ) : (
            <div className="details">No video available</div>
          )}

          {qcResult ? (
            <div style={{ marginTop: 16 }}>
              <h3 style={{ marginTop: 0 }}>Quality Control</h3>
              <div>
                <strong>Decision:</strong> {qcResult.decision ?? 'Publish'} ({qcResult.overall_score ?? 0}/10)
              </div>
              <div style={{ marginTop: 8, opacity: 0.95 }}>
                <div>
                  <strong>Post feedback:</strong> {qcResult.post_feedback ?? ''}
                </div>
                <div style={{ marginTop: 6 }}>
                  <strong>Video feedback:</strong> {qcResult.video_feedback ?? ''}
                </div>
              </div>
            </div>
          ) : null}

          <details style={{ marginTop: 16 }}>
            <summary className="summary">Raw pipeline output (for judges)</summary>
            <pre style={{ whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(
                {
                  retrieval_pack: retrievalPack,
                  content_draft: contentDraft ? { ...contentDraft, video_brief: contentDraft.video_brief } : null,
                  final_output: finalOutput,
                  video_output: videoOutput,
                  qc: qcResult,
                },
                null,
                2
              )}
            </pre>
          </details>
        </section>
      ) : null}

      </>) : null}
      </div>
    </div>
  )
}

export default App
