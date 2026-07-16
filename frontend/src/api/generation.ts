import type { ClientRecord } from './client'

export interface GenerationFact {
  label: string
  value: string
}

export interface GenerationRequest {
  appointmentDate: string
  client: Pick<ClientRecord, 'ehrId' | 'name'>
  facts: GenerationFact[]
  noteType: string
  plan: Pick<ClientRecord['plan'], 'goal' | 'objective'>
  serviceType: string
  staffMember: string
}

export interface GenerationResult {
  latencyMs: number
  model: string
  note: string
}

export async function requestGroundedDraft(payload: GenerationRequest): Promise<GenerationResult> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 30_000)
  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw new Error(`Generation failed: ${response.status}`)
    const result = (await response.json()) as Partial<GenerationResult>
    if (!result.note || !result.model || typeof result.latencyMs !== 'number') {
      throw new Error('Generation returned an invalid response')
    }
    return result as GenerationResult
  } finally {
    window.clearTimeout(timeout)
  }
}
