import { useEffect, useMemo, useState } from 'react'
import './App.css'

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

function b64ToBlobUrl(b64: string, mime: string) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  const blob = new Blob([bytes], { type: mime })
  return URL.createObjectURL(blob)
}

function App() {
  const [topics, setTopics] = useState<string[]>([])
  const [topic, setTopic] = useState<string>('')
  const [platform, setPlatform] = useState<Platform>('linkedin')

  const [phase, setPhase] = useState<'idle' | 'post_running' | 'post_done' | 'video_running' | 'video_done'>('idle')

  const [retrievalPack, setRetrievalPack] = useState<any>(null)
  const [contentDraft, setContentDraft] = useState<any>(null)
  const [finalOutput, setFinalOutput] = useState<any>(null)

  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [videoOutput, setVideoOutput] = useState<any>(null)
  const [qcResult, setQcResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

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
    // reset local edits when new draft arrives
    if (contentDraft?.video_brief?.storyboard) {
      setEditedStoryboard(contentDraft.video_brief.storyboard)
      setEditedSsml(contentDraft.video_brief.ssml_script ?? '')
    }
  }, [contentDraft])

  const postImageUrl = useMemo(() => {
    const b64 = finalOutput?.image_b64
    if (!b64) return null
    // Imagen often returns jpeg, but we don’t know for sure; jpeg works for display in most cases
    return b64ToBlobUrl(b64, 'image/jpeg')
  }, [finalOutput])

  const videoUrl = useMemo(() => {
    const b64 = videoOutput?.video_b64
    if (!b64) return null
    return b64ToBlobUrl(b64, 'video/mp4')
  }, [videoOutput])

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
      body: JSON.stringify({ topic, platform }),
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
  }

  return (
    <div className="page">
      <div className="container">
        <header className="topbar">
          <div>
            <h2 className="brandTitle">NYC International Student AI Influencer</h2>
            <div className="brandTagline">Turn live sources into a post + storyboard + video.</div>
          </div>
          <button className="btn btnSecondary" onClick={resetAll}>
            Reset
          </button>
        </header>

        {error ? (
          <div className="errorBox">
            <strong>Error:</strong> {error}
          </div>
        ) : null}

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
                <div className="details">No image</div>
              )}
            </div>
            <div>
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                {finalOutput.body ?? finalOutput.caption ?? '(no post body)'}
              </pre>
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
      </div>
    </div>
  )
}

export default App
