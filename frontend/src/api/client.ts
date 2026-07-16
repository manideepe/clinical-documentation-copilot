export type PlanStatus = 'active' | 'expired'

export interface ClientRecord {
  id: string
  ehrId: string
  name: string
  preferredName: string
  pronouns: string
  dateOfBirth: string
  age: number
  avatar: string
  plan: {
    id: string
    status: PlanStatus
    effectiveDate: string
    endDate: string
    lastSynced: string
    goal: string
    objective: string
  }
}

export interface ClientResult {
  clients: ClientRecord[]
  source: 'ehr-api' | 'demo-fallback'
}

interface BackendPlan {
  external_id: string
  status: 'ACTIVE' | 'INACTIVE' | 'EXPIRED'
  effective_date: string
  expiration_date: string | null
  goals: string[]
  objectives: string[]
  source_updated_at: string
}

interface BackendClient {
  external_id: string
  given_name: string
  family_name: string
  date_of_birth: string
  is_active: boolean
  active_treatment_plan: BackendPlan | null
  latest_treatment_plan: BackendPlan | null
}

function displayDate(value: string | null): string {
  if (!value) return 'No end date'
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

function normalizeClient(item: BackendClient): ClientRecord {
  const plan = item.active_treatment_plan ?? item.latest_treatment_plan
  const initials = `${item.given_name[0] ?? ''}${item.family_name[0] ?? ''}`.toUpperCase()
  return {
    id: item.external_id,
    ehrId: item.external_id,
    name: `${item.given_name} ${item.family_name}`,
    preferredName: item.given_name,
    pronouns: 'not supplied',
    dateOfBirth: item.date_of_birth,
    age: calculateAge(item.date_of_birth),
    avatar: initials || '—',
    plan: {
      id: plan?.external_id ?? 'No synchronized plan',
      status: item.active_treatment_plan ? 'active' : 'expired',
      effectiveDate: plan ? displayDate(plan.effective_date) : 'Not available',
      endDate: plan ? displayDate(plan.expiration_date) : 'Not available',
      lastSynced: plan?.source_updated_at ?? 'Not available',
      goal: plan?.goals[0] ?? 'Additional treatment-plan documentation required.',
      objective: plan?.objectives[0] ?? 'Additional treatment-plan documentation required.',
    },
  }
}

const DEMO_CLIENTS: ClientRecord[] = [
  {
    id: 'client-001',
    ehrId: 'EHR-28419',
    name: 'Avery Morgan',
    preferredName: 'Avery',
    pronouns: 'they/them',
    dateOfBirth: '1992-08-14',
    age: 33,
    avatar: 'AM',
    plan: {
      id: 'TP-2026-0419',
      status: 'active',
      effectiveDate: 'Apr 19, 2026',
      endDate: 'Oct 19, 2026',
      lastSynced: '2 minutes ago',
      goal: 'Improve emotional regulation and reduce anxiety-related disruption.',
      objective:
        'Use two grounding strategies during periods of elevated anxiety on four of seven days each week.',
    },
  },
  {
    id: 'client-002',
    ehrId: 'EHR-19387',
    name: 'Jordan Lee',
    preferredName: 'Jordan',
    pronouns: 'she/her',
    dateOfBirth: '1988-02-03',
    age: 38,
    avatar: 'JL',
    plan: {
      id: 'TP-2025-1207',
      status: 'expired',
      effectiveDate: 'Dec 7, 2025',
      endDate: 'Jun 7, 2026',
      lastSynced: '2 minutes ago',
      goal: 'Increase use of coping skills for stress management.',
      objective: 'Previous objective is read-only until a new plan is activated.',
    },
  },
]

export async function loadClients(): Promise<ClientResult> {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'

  try {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 3500)
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}/clients`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    })
    window.clearTimeout(timeoutId)

    if (!response.ok) throw new Error(`Client sync failed: ${response.status}`)

    const body = (await response.json()) as { items?: BackendClient[] }
    const clients = body.items?.map(normalizeClient) ?? []
    if (!clients.length) throw new Error('No synchronized clients returned')
    return { clients, source: 'ehr-api' }
  } catch {
    return { clients: DEMO_CLIENTS, source: 'demo-fallback' }
  }
}
