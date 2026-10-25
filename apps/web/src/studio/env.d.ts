/// <reference types="vite/client" />

type ProviderConfig = {
  baseUrl: string
  model: string
  allowInsecure: boolean
  runtimeUrl: string
  configured: boolean
  keyPersisted: boolean
  encryptionAvailable: boolean
  capabilities?: ProviderCapabilities | null
}

type ProviderCapabilities = {
  chat: boolean
  tools: boolean
  vision: boolean
  checkedAt: number
  errors: Record<string, string>
}

type ArtifactRef = { uri: string; sha256: string; width?: number; height?: number; has_alpha?: boolean }
type ExportFormat = 'png' | 'jpeg' | 'webp'
type ExportSettings = {
  directory: string
  format: ExportFormat
  jpegQuality: number
  webpQuality: number
  jpegBackground: string
}
type ExportPayload = {
  media: ArtifactRef
  operation?: 'generate' | 'edit'
  seed?: number
  format?: ExportFormat
  quality?: number
  background?: string
}
type ExportResult = { cancelled: boolean; path?: string; format?: ExportFormat }

interface Window {
  visualLab: {
    platform?: 'web' | 'desktop'
    ui: {
      confirm(action: 'gallery-remove' | 'agent-clear' | 'character-remove' | 'lora-remove'): Promise<boolean>
    }
    runtime: {
      request(method: string, path: string, body?: unknown): Promise<any>
      upload(payload: { name: string; type: string; bytes: Uint8Array; sessionId: string }): Promise<any>
      artifactData(uri: string): Promise<string>
      preview(ref: ArtifactRef): Promise<string>
      jobPreview(jobId: string): Promise<string>
      saveUrl(url: string): Promise<ProviderConfig>
      uploadMedia(sessionId: string, file?: File): Promise<{ data: ArtifactRef } | null>
      mediaUrl(uri: string): Promise<string>
      saveMedia(uri: string): Promise<{ cancelled: boolean; path?: string }>
    }
    provider: {
      get(): Promise<ProviderConfig>
      save(config: { baseUrl: string; model: string; apiKey?: string; allowInsecure: boolean }): Promise<ProviderConfig>
      test(): Promise<ProviderCapabilities>
    }
    export: {
      getSettings(): Promise<ExportSettings>
      saveSettings(settings: Partial<ExportSettings>): Promise<ExportSettings>
      chooseFolder(): Promise<ExportSettings>
      saveAs(payload: ExportPayload): Promise<ExportResult>
      quickSave(payload: ExportPayload): Promise<ExportResult>
      showInFolder(filePath: string): Promise<boolean>
    }
    agent: {
      improve(prompt: string, mode?: 't2i' | 'i2i' | 'moss' | 't2v' | 'i2v' | 'r2v' | 'kandinsky' | 'song' | 'ace_song', references?: ArtifactRef[], seconds?: number): Promise<{
        prompt: string; lyrics?: string; audio_prompt?: string; bpm?: number; key?: string; time_signature?: string; language?: string }>
      start(payload: { prompt: string; session: string; references: ArtifactRef[] }): Promise<any>
      get(payload: { id?: string; session?: string }): Promise<any>
      cancel(id: string, jobId?: string): Promise<any>
      continue(id: string): Promise<any>
      onEvent(callback: (run: any) => void): () => void
      review(payload: { prompt: string; media: ArtifactRef }): Promise<{ verdict: string; suggestedPrompt: string | null; alpha: any }>
      directorPlan(payload: { brief: string; lyrics: string; analysis: any }): Promise<{ scenes: any[]; outbound: any }>
    }
    graph: {
      show(gpu: number, bounds: DOMRect | { x: number; y: number; width: number; height: number }): Promise<boolean>
      bounds(bounds: DOMRect | { x: number; y: number; width: number; height: number }): Promise<void>
      hide(): Promise<void>
    }
  }
}
