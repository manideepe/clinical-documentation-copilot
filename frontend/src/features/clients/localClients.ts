import type { ClientRecord } from '../../api/client'

export interface LocalClientDraft {
  dateOfBirth: string
  effectiveDate: string
  ehrId: string
  endDate: string
  goal: string
  name: string
  objective: string
  planId: string
  preferredName: string
  pronouns: string
}

const STORAGE_KEY = 'claritynote-local-test-clients-v1'

function displayDate(value: string): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`))
}

function calculateAge(dateOfBirth: string): number {
  const birth = new Date(`${dateOfBirth}T00:00:00Z`)
  const today = new Date()
  let age = today.getUTCFullYear() - birth.getUTCFullYear()
  const beforeBirthday =
    today.getUTCMonth() < birth.getUTCMonth() ||
    (today.getUTCMonth() === birth.getUTCMonth() && today.getUTCDate() < birth.getUTCDate())
  if (beforeBirthday) age -= 1
  return age
}

function isClientRecord(value: unknown): value is ClientRecord {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ClientRecord>
  return Boolean(
    typeof candidate.id === 'string' &&
      typeof candidate.name === 'string' &&
      typeof candidate.ehrId === 'string' &&
      candidate.plan &&
      typeof candidate.plan.id === 'string',
  )
}

export function createInitialClientDraft(): LocalClientDraft {
  return {
    dateOfBirth: '1990-01-01',
    effectiveDate: '2026-04-18',
    ehrId: '',
    endDate: '2027-04-18',
    goal: '',
    name: '',
    objective: '',
    planId: '',
    preferredName: '',
    pronouns: 'they/them',
  }
}

export function createLocalClient(draft: LocalClientDraft): ClientRecord {
  const nameParts = draft.name.trim().split(/\s+/)
  const initials = nameParts
    .slice(0, 2)
    .map((part) => part[0] ?? '')
    .join('')
    .toUpperCase()

  return {
    id: `local-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`,
    ehrId: draft.ehrId.trim(),
    name: draft.name.trim(),
    preferredName: draft.preferredName.trim() || nameParts[0] || draft.name.trim(),
    pronouns: draft.pronouns.trim(),
    dateOfBirth: draft.dateOfBirth,
    age: calculateAge(draft.dateOfBirth),
    avatar: initials || 'TC',
    plan: {
      id: draft.planId.trim(),
      status: 'active',
      effectiveDate: displayDate(draft.effectiveDate),
      endDate: displayDate(draft.endDate),
      lastSynced: 'Saved in this browser',
      goal: draft.goal.trim(),
      objective: draft.objective.trim(),
    },
  }
}

export function loadLocalClients(): ClientRecord[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as unknown
    return Array.isArray(parsed) ? parsed.filter(isClientRecord) : []
  } catch {
    return []
  }
}

export function saveLocalClients(clients: ClientRecord[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(clients.filter((client) => client.id.startsWith('local-'))))
}
