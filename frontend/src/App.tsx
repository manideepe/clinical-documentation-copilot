import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  AlertTriangle,
  CalendarDays,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Copy,
  FileCheck2,
  FileText,
  History,
  LayoutDashboard,
  LockKeyhole,
  Mic2,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  UserRound,
  Users,
  X,
} from 'lucide-react'
import { loadClients, type ClientRecord } from './api/client'
import { requestGroundedDraft } from './api/generation'
import {
  createInitialClientDraft,
  createLocalClient,
  loadLocalClients,
  saveLocalClients,
  type LocalClientDraft,
} from './features/clients/localClients'
import {
  formatElapsedTime,
  splitTranscriptIntoFacts,
  useLiveTranscription,
} from './features/voice/useLiveTranscription'

const NOTE_TYPES = [
  'Case Management Note',
  'Initial Child Assessment',
  'Child Assessment Update',
  'Initial Adult Assessment',
  'Adult Assessment Update',
  'Counselor Note',
  'Evaluation and Management (E&M) Note',
  'Nursing Progress Note',
] as const

type NoteType = (typeof NOTE_TYPES)[number]
type DocumentationMode = 'text' | 'voice'
type AppointmentStatus =
  | 'Scheduled'
  | 'In Progress'
  | 'Documentation Pending'
  | 'Completed'
  | 'Cancelled'

interface FactField {
  id: string
  label: string
  placeholder: string
  value: string
}

interface AuditItem {
  id: number
  title: string
  detail: string
  time: string
  state: 'done' | 'current' | 'pending'
}

interface GenerationDetails {
  latencyMs: number
  model: string
  source: 'ollama' | 'deterministic'
}

const INITIAL_FACTS: FactField[] = [
  {
    id: 'topics',
    label: 'Topics discussed',
    placeholder: 'What was discussed during the session?',
    value: 'Reviewed anxiety triggers at work and recent changes to sleep routine.',
  },
  {
    id: 'services',
    label: 'Services provided',
    placeholder: 'What service or support was provided?',
    value: 'Provided skills coaching and psychoeducation on the stress response.',
  },
  {
    id: 'response',
    label: 'Client response',
    placeholder: 'How did the client respond?',
    value: 'Client was engaged and practiced the 5-4-3-2-1 grounding exercise.',
  },
  {
    id: 'progress',
    label: 'Progress observed',
    placeholder: 'Document only progress directly observed or reported.',
    value: 'Client reported using paced breathing on three days this week.',
  },
  {
    id: 'interventions',
    label: 'Interventions used',
    placeholder: 'Which interventions were used?',
    value: 'Modeled paced breathing and rehearsed a brief grounding sequence.',
  },
  {
    id: 'concerns',
    label: 'Concerns or barriers',
    placeholder: 'Enter concerns, barriers, or “none reported.”',
    value: 'Client identified inconsistent sleep as a barrier; no acute concerns reported.',
  },
  {
    id: 'next-steps',
    label: 'Goals and next steps',
    placeholder: 'What goal was addressed and what happens next?',
    value: 'Continue daily grounding practice and review frequency at the next visit.',
  },
]

const EMPTY_FACTS: FactField[] = INITIAL_FACTS.map((fact) => ({ ...fact, value: '' }))

const INITIAL_AUDIT: AuditItem[] = [
  {
    id: 1,
    title: 'Client record synchronized',
    detail: 'Demographics matched to the EHR master record.',
    time: '11:31 AM',
    state: 'done',
  },
  {
    id: 2,
    title: 'Latest treatment plan verified',
    detail: 'Only the most recent active plan is available to generation.',
    time: '11:32 AM',
    state: 'done',
  },
]

function buildGeneratedNote(
  client: ClientRecord,
  noteType: NoteType,
  facts: FactField[],
  appointmentDate: string,
  staffMember: string,
  serviceType: string,
) {
  const fact = Object.fromEntries(facts.map((item) => [item.id, item.value]))

  return `${noteType.toUpperCase()}

Service date: ${appointmentDate}
Service: ${serviceType}
Staff member: ${staffMember}
Client: ${client.name} (${client.ehrId})

SESSION FOCUS
${fact.topics || '[Additional documentation required]'}

SERVICES AND INTERVENTIONS
${fact.services || '[Additional documentation required]'} ${fact.interventions || ''}`.trimEnd() + `

CLIENT RESPONSE
${fact.response || '[Additional documentation required]'}

PROGRESS TOWARD TREATMENT OBJECTIVE
${fact.progress || '[Additional documentation required]'} This information relates to the current objective: ${client.plan.objective}

BARRIERS / CONCERNS
${fact.concerns || '[Additional documentation required]'}

PLAN
${fact['next-steps'] || '[Additional documentation required]'}`
}

function App() {
  const [clients, setClients] = useState<ClientRecord[]>([])
  const [selectedClientId, setSelectedClientId] = useState('client-001')
  const [dataSource, setDataSource] = useState<'ehr-api' | 'demo-fallback'>(
    'demo-fallback',
  )
  const [searchTerm, setSearchTerm] = useState('')
  const [showClientResults, setShowClientResults] = useState(false)
  const [appointmentDate, setAppointmentDate] = useState('2026-04-21')
  const [staffMember, setStaffMember] = useState('Sarah Kim, LCSW')
  const [serviceType, setServiceType] = useState('Individual Counseling · 53 min')
  const [noteType, setNoteType] = useState<NoteType>('Counselor Note')
  const [mode, setMode] = useState<DocumentationMode>('text')
  const [facts, setFacts] = useState(INITIAL_FACTS)
  const [note, setNote] = useState('')
  const [status, setStatus] = useState<AppointmentStatus>('In Progress')
  const [reviewed, setReviewed] = useState(false)
  const [approved, setApproved] = useState(false)
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generationDetails, setGenerationDetails] = useState<GenerationDetails | null>(null)
  const [savedPending, setSavedPending] = useState(false)
  const [auditItems, setAuditItems] = useState(INITIAL_AUDIT)
  const [showClientModal, setShowClientModal] = useState(false)
  const [showProfileModal, setShowProfileModal] = useState(false)
  const [showHelpModal, setShowHelpModal] = useState(false)
  const [supervisorNotified, setSupervisorNotified] = useState(false)
  const [clientDraft, setClientDraft] = useState<LocalClientDraft>(createInitialClientDraft)
  const [voiceMappingError, setVoiceMappingError] = useState('')
  const generationToken = useRef(0)
  const voice = useLiveTranscription()

  useEffect(() => {
    let mounted = true
    void loadClients().then((result) => {
      if (!mounted) return
      setClients([...result.clients, ...loadLocalClients()])
      setDataSource(result.source)
    })
    return () => {
      mounted = false
      generationToken.current += 1
    }
  }, [])

  const client =
    clients.find((item) => item.id === selectedClientId) ?? clients[0]
  const planIsActive = client?.plan.status === 'active'

  const filteredClients = useMemo(() => {
    const normalizedTerm = searchTerm.trim().toLowerCase()
    if (!normalizedTerm) return clients
    return clients.filter(
      (item) =>
        item.name.toLowerCase().includes(normalizedTerm) ||
        item.ehrId.toLowerCase().includes(normalizedTerm),
    )
  }, [clients, searchTerm])

  const completedFacts = facts.filter((item) => item.value.trim()).length
  const workflowStage = status === 'Completed' ? 5 : note ? 4 : 3
  const canGenerate =
    planIsActive &&
    mode === 'text' &&
    completedFacts >= 6 &&
    status !== 'Completed' &&
    !generating

  function activateClient(nextClient: ClientRecord) {
    generationToken.current += 1
    setSelectedClientId(nextClient.id)
    setSearchTerm('')
    setShowClientResults(false)
    setMode('text')
    setReviewed(false)
    setApproved(false)
    setCopied(false)
    setCopyError(false)
    setGenerating(false)
    setGenerationDetails(null)
    setSavedPending(false)
    setSupervisorNotified(false)
    setShowProfileModal(false)
    setVoiceMappingError('')
    voice.clear()
    setStatus('In Progress')
    setFacts(nextClient.id.startsWith('local-') ? EMPTY_FACTS : INITIAL_FACTS)
    setAppointmentDate('2026-04-21')
    setStaffMember('Sarah Kim, LCSW')
    setServiceType('Individual Counseling · 53 min')

    if (nextClient.plan.status === 'active') {
      setNote('')
      setAuditItems(INITIAL_AUDIT)
    } else {
      setNote('')
      setAuditItems([
        INITIAL_AUDIT[0],
        {
          id: 4,
          title: 'Expired treatment plan detected',
          detail: 'Voice capture and AI generation were automatically blocked.',
          time: '11:32 AM',
          state: 'current',
        },
      ])
    }
  }

  function selectClient(clientId: string) {
    const nextClient = clients.find((item) => item.id === clientId)
    if (nextClient) activateClient(nextClient)
  }

  function updateClientDraft<K extends keyof LocalClientDraft>(
    field: K,
    value: LocalClientDraft[K],
  ) {
    setClientDraft((current) => ({ ...current, [field]: value }))
  }

  function addLocalClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextClient = createLocalClient(clientDraft)
    const nextClients = [...clients, nextClient]
    setClients(nextClients)
    saveLocalClients(nextClients)
    activateClient(nextClient)
    setClientDraft(createInitialClientDraft())
    setShowClientModal(false)
  }
  function invalidateDraft() {
    generationToken.current += 1
    setGenerating(false)
    setGenerationDetails(null)
    setNote('')
    setReviewed(false)
    setApproved(false)
    setCopied(false)
    setCopyError(false)
    setStatus('In Progress')
  }

  function updateFact(id: string, value: string) {
    setFacts((current) =>
      current.map((item) => (item.id === id ? { ...item, value } : item)),
    )
    invalidateDraft()
  }

  function changeNoteType(nextType: NoteType) {
    setNoteType(nextType)
    invalidateDraft()
  }

  function changeMode(nextMode: DocumentationMode) {
    if (status === 'Completed') return
    if (nextMode !== 'voice') voice.stop()
    setMode(nextMode)
    setVoiceMappingError('')
    invalidateDraft()
  }

  function useVoiceTranscript() {
    const segments = splitTranscriptIntoFacts(voice.transcript)
    if (segments.length < 6) {
      setVoiceMappingError(
        'Add at least six complete statements, ending each one with a period, before continuing.',
      )
      return
    }

    const values =
      segments.length === 6
        ? [...segments.slice(0, 5), '', segments[5]]
        : [...segments.slice(0, 6), segments.slice(6).join(' ')]

    setFacts(
      EMPTY_FACTS.map((fact, index) => ({
        ...fact,
        value: values[index] ?? '',
      })),
    )
    voice.stop()
    setMode('text')
    setVoiceMappingError('')
    invalidateDraft()
  }

  async function generateNote() {
    if (!client || !canGenerate) return
    setGenerating(true)
    setGenerationDetails(null)
    setReviewed(false)
    setApproved(false)
    setCopied(false)
    setCopyError(false)
    const requestToken = ++generationToken.current
    let generatedNote = ''
    let details: GenerationDetails

    try {
      const result = await requestGroundedDraft({
        appointmentDate,
        client: { ehrId: client.ehrId, name: client.name },
        facts: facts.map(({ label, value }) => ({ label, value })),
        noteType,
        plan: { goal: client.plan.goal, objective: client.plan.objective },
        serviceType,
        staffMember,
      })
      generatedNote = result.note
      details = { latencyMs: result.latencyMs, model: result.model, source: 'ollama' }
    } catch {
      generatedNote = buildGeneratedNote(
        client,
        noteType,
        facts,
        appointmentDate,
        staffMember,
        serviceType,
      )
      details = { latencyMs: 0, model: 'Grounded template', source: 'deterministic' }
    }

    if (generationToken.current !== requestToken) return
    setNote(generatedNote)
    setGenerationDetails(details)
    setGenerating(false)
    setStatus('Documentation Pending')
    setAuditItems((items) => [
      ...items.filter((item) => item.title !== 'Clinical draft generated'),
      {
        id: Date.now(),
        title: 'Clinical draft generated',
        detail: `${noteType} grounded in ${completedFacts} clinician facts using ${details.model}.`,
        time: 'Just now',
        state: 'current',
      },
    ])
  }

  function savePendingSummary() {
    setSavedPending(true)
    setStatus('Documentation Pending')
    setAuditItems((items) => [
      ...items.filter((item) => item.title !== 'Session facts saved'),
      {
        id: Date.now(),
        title: 'Session facts saved',
        detail: 'Original facts preserved; waiting for a new active treatment plan.',
        time: 'Just now',
        state: 'current',
      },
    ])
  }

  function notifySupervisor() {
    if (supervisorNotified) return
    setSupervisorNotified(true)
    setAuditItems((items) => [
      ...items.filter((item) => item.title !== 'Supervisor alert logged'),
      {
        id: Date.now(),
        title: 'Supervisor alert logged',
        detail: 'A local workflow alert was added for the expired treatment plan.',
        time: 'Just now',
        state: 'current',
      },
    ])
  }

  function approveNote() {
    if (!reviewed || !note) return
    setApproved(true)
    setAuditItems((items) => [
      ...items,
      {
        id: Date.now(),
        title: 'Draft approved by clinician',
        detail: 'Approval is recorded; the note remains editable until completion.',
        time: 'Just now',
        state: 'done',
      },
    ])
  }

  async function copyNote() {
    if (!approved || !note) return
    setCopyError(false)
    try {
      if (!navigator.clipboard) throw new Error('Clipboard API unavailable')
      await navigator.clipboard.writeText(note)
      setCopied(true)
    } catch {
      setCopied(false)
      setCopyError(true)
    }
  }

  function completeAppointment() {
    if (!approved) return
    setStatus('Completed')
    setAuditItems((items) => [
      ...items,
      {
        id: Date.now(),
        title: 'Appointment completed and locked',
        detail: 'Final status and timestamps were added to the audit record.',
        time: 'Just now',
        state: 'done',
      },
    ])
  }

  if (!client) {
    return (
      <main className="loading-screen" aria-live="polite">
        <RefreshCw className="spin" aria-hidden="true" />
        <p>Synchronizing clinical workspace…</p>
      </main>
    )
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <FileCheck2 size={22} />
          </div>
          <div>
            <strong>ClarityNote</strong>
            <span>Care documentation</span>
          </div>
        </div>

        <nav className="primary-nav" aria-label="Primary navigation">
          <a href="#workspace" className="nav-link active" aria-current="page">
            <LayoutDashboard size={18} aria-hidden="true" />
            Documentation
          </a>
          <a href="#clients" className="nav-link">
            <Users size={18} aria-hidden="true" />
            Clients
          </a>
          <a href="#audit" className="nav-link">
            <History size={18} aria-hidden="true" />
            Audit trail
          </a>
        </nav>

        <div className="topbar-actions">
          <div className="workspace-security">
            <ShieldCheck size={17} aria-hidden="true" />
            <span>Clinical workspace</span>
          </div>
          <div className="user-card">
            <div className="avatar small">SK</div>
            <div>
              <strong>Sarah Kim, LCSW</strong>
              <span>Counselor</span>
            </div>
          </div>
        </div>
      </header>

      <div className="workspace-frame">
        <main className="main-content" id="workspace">
          <header className="page-header">
            <div>
              <p className="breadcrumb">Documentation / Current appointment</p>
              <h1>Appointment workspace</h1>
              <p className="page-subtitle">
                Capture the visit, review the clinical draft, and complete the record.
              </p>
            </div>
            <div className="sync-state" title="Connection status">
              <span className="sync-dot" aria-hidden="true" />
              <span>
                <strong>{dataSource === 'ehr-api' ? 'EHR connected' : 'Workspace ready'}</strong>
                <small>Updated 2 minutes ago</small>
              </span>
            </div>
          </header>

          <section className="workflow-progress" aria-label="Documentation progress">
            {[
              ['1', 'Client & plan'],
              ['2', 'Appointment'],
              ['3', 'Session facts'],
              ['4', 'Review & approve'],
            ].map(([number, label]) => {
              const numericStep = Number(number)
              const stepState =
                numericStep < workflowStage
                  ? 'complete'
                  : numericStep === workflowStage
                    ? 'current'
                    : 'upcoming'

              return (
                <div
                  className={`progress-step ${stepState}`}
                  key={number}
                  aria-current={stepState === 'current' ? 'step' : undefined}
                >
                  <span className="step-number" aria-hidden="true">
                    {stepState === 'complete' ? <Check size={14} /> : number}
                  </span>
                  <span>{label}</span>
                </div>
              )
            })}
          </section>

        <section className="client-plan-card" id="clients">
          <div className="client-selector">
            <label htmlFor="client-search">Client</label>
            <div className="search-wrap">
              <Search size={17} aria-hidden="true" />
              <input
                id="client-search"
                value={searchTerm}
                onChange={(event) => {
                  setSearchTerm(event.target.value)
                  setShowClientResults(true)
                }}
                onFocus={() => setShowClientResults(true)}
                placeholder="Search by name or EHR ID"
                autoComplete="off"
              />
              {showClientResults && (
                <div className="search-results" role="listbox" aria-label="Clients">
                  {filteredClients.length ? (
                    filteredClients.map((item) => (
                      <button
                        type="button"
                        role="option"
                        aria-selected={item.id === client.id}
                        key={item.id}
                        onClick={() => selectClient(item.id)}
                      >
                        <span className="avatar tiny">{item.avatar}</span>
                        <span>
                          <strong>{item.name}</strong>
                          <small>{item.ehrId}</small>
                        </span>
                        <span className={`mini-status ${item.plan.status}`}>
                          {item.plan.status}
                        </span>
                      </button>
                    ))
                  ) : (
                    <p>No matching clients</p>
                  )}
                </div>
              )}
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Add client"
              title="Create a test client"
              onClick={() => setShowClientModal(true)}
            >
              <Plus size={18} />
            </button>
          </div>

          <div className="selected-client">
            <div className="avatar">{client.avatar}</div>
            <div className="client-identity">
              <div className="name-row">
                <h2>{client.name}</h2>
                <span>{client.pronouns}</span>
              </div>
              <p>
                DOB {client.dateOfBirth} · {client.age} years · {client.ehrId}
              </p>
            </div>
            <button
              className="text-button"
              type="button"
              onClick={() => setShowProfileModal(true)}
            >
              View client profile
            </button>
          </div>

          <div className={`plan-summary ${planIsActive ? 'active' : 'expired'}`}>
            <div className="plan-heading">
              <div className="plan-icon" aria-hidden="true">
                {planIsActive ? <FileCheck2 size={19} /> : <AlertTriangle size={19} />}
              </div>
              <div>
                <p>Latest treatment plan</p>
                <h3>{client.plan.id}</h3>
              </div>
              <span className={`status-pill ${client.plan.status}`}>
                {planIsActive ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                {planIsActive ? 'Active' : 'Expired'}
              </span>
            </div>
            <dl className="plan-dates">
              <div>
                <dt>Effective</dt>
                <dd>{client.plan.effectiveDate}</dd>
              </div>
              <div>
                <dt>{planIsActive ? 'Review by' : 'Expired on'}</dt>
                <dd>{client.plan.endDate}</dd>
              </div>
            </dl>
            <div className="goal-block">
              <div>
                <span>Goal 1</span>
                <p>{client.plan.goal}</p>
              </div>
              <div>
                <span>Objective 1.1</span>
                <p>{client.plan.objective}</p>
              </div>
            </div>
          </div>

          {!planIsActive && (
            <div className="expired-alert" role="alert">
              <AlertTriangle size={20} aria-hidden="true" />
              <div>
                <strong>Treatment plan expired</strong>
                <p>
                  Continue the appointment and save session facts. Voice capture and AI note
                  generation will remain unavailable until a new plan is active.
                </p>
              </div>
              <button
                type="button"
                className="text-button warning"
                disabled={supervisorNotified}
                onClick={notifySupervisor}
              >
                {supervisorNotified ? 'Supervisor alert logged' : 'Notify supervisor'}
              </button>
            </div>
          )}
        </section>

        <section className="appointment-card" aria-labelledby="appointment-heading">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Appointment setup</p>
              <h2 id="appointment-heading">Session details</h2>
            </div>
            <label className={`status-select ${status.toLowerCase().replaceAll(' ', '-')}`}>
              <span className="sr-only">Appointment status</span>
              <select
                value={status}
                disabled
                aria-label="Appointment status (controlled by workflow)"
              >
                <option>Scheduled</option>
                <option>In Progress</option>
                <option>Documentation Pending</option>
                <option>Completed</option>
                <option>Cancelled</option>
              </select>
            </label>
          </div>

          <div className="appointment-grid">
            <label>
              Appointment date
              <span className="input-with-icon">
                <CalendarDays size={16} aria-hidden="true" />
                <input
                  type="date"
                  value={appointmentDate}
                  disabled={status === 'Completed'}
                  onChange={(event) => {
                    setAppointmentDate(event.target.value)
                    invalidateDraft()
                  }}
                />
              </span>
            </label>
            <label>
              Staff member
              <span className="input-with-icon">
                <UserRound size={16} aria-hidden="true" />
                <select
                  value={staffMember}
                  disabled={status === 'Completed'}
                  onChange={(event) => {
                    setStaffMember(event.target.value)
                    invalidateDraft()
                  }}
                >
                  <option>Sarah Kim, LCSW</option>
                  <option>Michael Ortiz, RN</option>
                  <option>Priya Shah, MD</option>
                </select>
              </span>
            </label>
            <label>
              Service type
              <select
                value={serviceType}
                disabled={status === 'Completed'}
                onChange={(event) => {
                  setServiceType(event.target.value)
                  invalidateDraft()
                }}
              >
                <option>Individual Counseling · 53 min</option>
                <option>Case Management · 45 min</option>
                <option>Medication Management · 30 min</option>
              </select>
            </label>
            <label>
              Note type
              <select
                value={noteType}
                disabled={status === 'Completed'}
                onChange={(event) => changeNoteType(event.target.value as NoteType)}
              >
                {NOTE_TYPES.map((type) => (
                  <option key={type}>{type}</option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <div className="documentation-grid">
          <section className="documentation-input" aria-labelledby="document-heading">
            <div className="section-heading input-heading">
              <div>
                <p className="section-kicker">Document the session</p>
                <h2 id="document-heading">Choose an input method</h2>
              </div>
              <span className="fact-count">{completedFacts} of 7 facts added</span>
            </div>

            <div className="mode-switch" role="group" aria-label="Documentation method">
              <button
                type="button"
                className={mode === 'text' ? 'selected' : ''}
                aria-pressed={mode === 'text'}
                disabled={status === 'Completed'}
                onClick={() => changeMode('text')}
              >
                <FileText size={19} aria-hidden="true" />
                <span>
                  <strong>Text summary</strong>
                  <small>Enter 6–7 factual bullet points</small>
                </span>
                {mode === 'text' && <CheckCircle2 size={18} className="mode-check" />}
              </button>
              <button
                type="button"
                className={mode === 'voice' ? 'selected' : ''}
                aria-pressed={mode === 'voice'}
                disabled={!planIsActive || status === 'Completed'}
                onClick={() => changeMode('voice')}
                aria-describedby={!planIsActive ? 'voice-disabled-reason' : undefined}
              >
                <Mic2 size={19} aria-hidden="true" />
                <span>
                  <strong>Voice summary</strong>
                  <small>{planIsActive ? 'Live microphone transcription' : 'Unavailable — plan expired'}</small>
                </span>
                {mode === 'voice' && <CheckCircle2 size={18} className="mode-check" />}
                {!planIsActive && <LockKeyhole size={16} className="mode-lock" />}
              </button>
            </div>
            {!planIsActive && (
              <p className="voice-disabled-reason" id="voice-disabled-reason">
                No audio can be recorded, uploaded, processed, or stored while the treatment plan
                is expired.
              </p>
            )}

            {mode === 'text' ? (
              <div className="facts-list">
                <div className="facts-instructions">
                  <Sparkles size={17} aria-hidden="true" />
                  <p>
                    Enter only what happened. Your wording is preserved as the factual source for
                    the draft.
                  </p>
                </div>
                {facts.map((fact, index) => (
                  <label className="fact-field" key={fact.id}>
                    <span className="fact-number">{index + 1}</span>
                    <span className="fact-label">
                      {fact.label}
                      <span className="optional">{index === 5 ? 'Optional' : 'Required'}</span>
                    </span>
                    <textarea
                      rows={2}
                      value={fact.value}
                      disabled={status === 'Completed'}
                      placeholder={fact.placeholder}
                      onChange={(event) => updateFact(fact.id, event.target.value)}
                    />
                  </label>
                ))}
              </div>
            ) : (
              <div className="voice-panel">
                <div className="voice-live-header">
                  <div className={`mic-orb ${voice.isListening ? 'recording' : ''}`}>
                    <Mic2 size={24} aria-hidden="true" />
                  </div>
                  <div>
                    <p className="section-kicker">Live session capture</p>
                    <h3>{voice.isListening ? 'Listening now' : 'Voice summary'}</h3>
                    <p>
                      {voice.isListening
                        ? 'Speak naturally. Final phrases appear in the transcript as you talk.'
                        : 'Allow microphone access, then speak at least six concise factual statements.'}
                    </p>
                  </div>
                  <div className="voice-timer" aria-label="Recording duration">
                    <span className={voice.isListening ? 'live-dot' : ''} aria-hidden="true" />
                    <strong>{formatElapsedTime(voice.elapsedSeconds)}</strong>
                    <small>{voice.isListening ? 'Live' : 'Ready'}</small>
                  </div>
                </div>

                {!voice.supported && (
                  <div className="voice-support-notice" role="status">
                    <AlertTriangle size={18} aria-hidden="true" />
                    <p>
                      This browser does not offer live speech recognition. You can still type or
                      paste a transcript below and continue the workflow.
                    </p>
                  </div>
                )}

                <label className="voice-transcript-label" htmlFor="live-transcript">
                  <span>
                    <strong>Live transcript</strong>
                    <small>Use one complete statement per fact.</small>
                  </span>
                  <textarea
                    id="live-transcript"
                    aria-label="Live transcript"
                    rows={12}
                    value={voice.transcript}
                    disabled={status === 'Completed'}
                    placeholder="Your live transcript will appear here. You can also type or paste a summary."
                    onChange={(event) => {
                      voice.setTranscript(event.target.value)
                      setVoiceMappingError('')
                    }}
                  />
                </label>

                {voice.interimTranscript && (
                  <div className="interim-transcript" aria-live="polite">
                    <span>Hearing</span>
                    {voice.interimTranscript}
                  </div>
                )}

                {voice.error && (
                  <p className="voice-error" role="alert">
                    {voice.error}
                  </p>
                )}

                <div className="voice-controls">
                  {voice.isListening ? (
                    <button
                      type="button"
                      className="secondary-button danger"
                      onClick={voice.stop}
                    >
                      Stop listening
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => void voice.start()}
                      disabled={!voice.supported || voice.isRequesting}
                    >
                      <Mic2 size={17} />
                      {voice.isRequesting ? 'Requesting microphone…' : 'Start live transcription'}
                    </button>
                  )}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={voice.clear}
                    disabled={!voice.transcript && !voice.interimTranscript}
                  >
                    Clear transcript
                  </button>
                </div>

                <div className="voice-privacy">
                  <ShieldCheck size={17} aria-hidden="true" />
                  <p>
                    ClarityNote does not save microphone audio. Speech processing is provided by
                    the browser; review its voice-service policy before using sensitive data.
                  </p>
                </div>

                {voiceMappingError && (
                  <p className="voice-error" role="alert">
                    {voiceMappingError}
                  </p>
                )}

                <button
                  type="button"
                  className="voice-use-button"
                  onClick={useVoiceTranscript}
                  disabled={!voice.transcript.trim()}
                >
                  <CheckCircle2 size={17} />
                  Use transcript in session facts
                </button>
              </div>
            )}

            <div className="input-actions">
              <div>
                <span className={`validation-dot ${completedFacts >= 6 ? 'valid' : ''}`} />
                {completedFacts >= 6
                  ? 'Minimum factual input met'
                  : `${6 - completedFacts} more facts required`}
              </div>
              {planIsActive ? (
                <button
                  className="primary-button"
                  type="button"
                  onClick={generateNote}
                  disabled={!canGenerate}
                >
                  {generating ? (
                    <RefreshCw className="spin" size={17} />
                  ) : (
                    <Sparkles size={17} />
                  )}
                  {generating ? 'Building grounded draft…' : 'Generate clinical note'}
                </button>
              ) : (
                <button
                  className="primary-button amber"
                  type="button"
                  onClick={savePendingSummary}
                  disabled={completedFacts < 6}
                >
                  <FileCheck2 size={17} />
                  {savedPending ? 'Session facts saved' : 'Save session facts'}
                </button>
              )}
            </div>
          </section>

          <section className="note-workspace" aria-labelledby="note-preview-heading">
            <div className="note-header">
              <div>
                <p className="section-kicker">Clinician review required</p>
                <h2 id="note-preview-heading">Generated note</h2>
              </div>
              {note && (
                <span className="draft-badge">
                  <Clock3 size={14} />
                  {status === 'Completed' ? 'Final · locked' : 'Draft · editable'}
                </span>
              )}
            </div>

            {planIsActive && note ? (
              <>
                <div className="grounding-strip">
                  <ShieldCheck size={18} aria-hidden="true" />
                  <div>
                    <strong>Draft assembled from displayed sources</strong>
                    <p>
                      Current plan · {completedFacts} staff facts · appointment details · {noteType}
                    </p>
                  </div>
                  <span>
                    {generationDetails?.source === 'ollama'
                      ? `${generationDetails.model} · ${(generationDetails.latencyMs / 1000).toFixed(1)}s`
                      : 'Grounded safety fallback'}
                  </span>
                </div>
                <label className="note-editor-label" htmlFor="note-editor">
                  Edit note content
                </label>
                <textarea
                  id="note-editor"
                  className="note-editor"
                  value={note}
                  disabled={status === 'Completed'}
                  onChange={(event) => {
                    setNote(event.target.value)
                    setReviewed(false)
                    setApproved(false)
                  }}
                  spellCheck="true"
                />
                <div className="editor-meta">
                  <span>{note.split(/\s+/).filter(Boolean).length} words</span>
                  <span>
                    <CheckCircle2 size={14} /> No diagnosis added automatically
                  </span>
                </div>

                <div className="review-panel">
                  <label className="review-check">
                    <input
                      type="checkbox"
                      checked={reviewed}
                      disabled={approved || status === 'Completed'}
                      onChange={(event) => setReviewed(event.target.checked)}
                    />
                    <span>
                      <strong>I reviewed this entire note</strong>
                      <small>I confirm it is accurate and ready for approval.</small>
                    </span>
                  </label>
                  <div className="review-actions">
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={approveNote}
                      disabled={!reviewed || approved}
                    >
                      {approved ? <Check size={17} /> : <ClipboardCheck size={17} />}
                      {approved ? 'Approved' : 'Approve note'}
                    </button>
                    <button
                      className="primary-button"
                      type="button"
                      onClick={copyNote}
                      disabled={!approved}
                    >
                      {copied ? <Check size={17} /> : <Copy size={17} />}
                      {copied ? 'Copied' : 'Copy note'}
                    </button>
                  </div>
                  {copyError && (
                    <p className="copy-error" role="status">
                      Clipboard access was blocked. Select the note text and copy it manually.
                    </p>
                  )}
                  {approved && (
                    <button
                      className="complete-button"
                      type="button"
                      onClick={completeAppointment}
                      disabled={status === 'Completed'}
                    >
                      <LockKeyhole size={15} />
                      {status === 'Completed' ? 'Appointment completed' : 'Mark appointment completed'}
                    </button>
                  )}
                </div>
              </>
            ) : (
              <div className="note-empty">
                <div className={planIsActive ? 'empty-icon' : 'empty-icon warning'}>
                  {planIsActive ? <FileText size={27} /> : <LockKeyhole size={27} />}
                </div>
                <h3>
                  {planIsActive ? 'Ready when your session facts are' : 'Documentation pending'}
                </h3>
                <p>
                  {planIsActive
                    ? 'Add at least six factual points, then generate an editable clinical draft.'
                    : 'Saved facts will remain unchanged. Generation becomes available only after a new active plan synchronizes.'}
                </p>
                {!planIsActive && (
                  <div className="pending-receipt">
                    <span>{savedPending ? <CheckCircle2 size={16} /> : <Clock3 size={16} />}</span>
                    <div>
                      <strong>{savedPending ? 'Facts saved' : 'Waiting for treatment plan'}</strong>
                      <small>
                        {savedPending
                          ? '7 source facts preserved · just now'
                          : 'Save at least 6 facts to preserve this session'}
                      </small>
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>

        <section className="audit-card" id="audit" aria-labelledby="audit-heading">
          <div className="audit-heading">
            <div>
              <p className="section-kicker">Traceability</p>
              <h2 id="audit-heading">Appointment activity</h2>
            </div>
            <div className="audit-protection">
              <LockKeyhole size={15} /> Protected activity log
            </div>
          </div>
          <div className="audit-list">
            {auditItems.map((item) => (
              <div className="audit-item" key={item.id}>
                <span className={`audit-marker ${item.state}`}>
                  {item.state === 'done' ? <Check size={13} /> : null}
                </span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </div>
                <time>{item.time}</time>
              </div>
            ))}
          </div>
        </section>

          <footer className="app-footer">
            <span>
              <ShieldCheck size={16} /> Review controls enabled
            </span>
            <span>Automatic sign-out in 14:32</span>
            <button type="button" onClick={() => setShowHelpModal(true)}>
              Help and support
            </button>
          </footer>
        </main>
      </div>

      {showProfileModal && (
        <div className="modal-backdrop" role="presentation">
          <section
            className="client-modal profile-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="profile-modal-title"
          >
            <div className="modal-header">
              <div>
                <p className="section-kicker">Client record</p>
                <h2 id="profile-modal-title">{client.name}</h2>
              </div>
              <button
                className="close-button"
                type="button"
                aria-label="Close client profile"
                onClick={() => setShowProfileModal(false)}
              >
                <X size={20} />
              </button>
            </div>

            <div className="profile-modal-body">
              <div className="profile-identity">
                <div className="avatar profile-avatar">{client.avatar}</div>
                <div>
                  <h3>{client.preferredName}</h3>
                  <p>{client.pronouns}</p>
                </div>
                <span className={`status-pill ${client.plan.status}`}>
                  {planIsActive ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                  {planIsActive ? 'Active plan' : 'Plan expired'}
                </span>
              </div>

              <dl className="profile-details">
                <div>
                  <dt>Record ID</dt>
                  <dd>{client.ehrId}</dd>
                </div>
                <div>
                  <dt>Date of birth</dt>
                  <dd>{client.dateOfBirth}</dd>
                </div>
                <div>
                  <dt>Age</dt>
                  <dd>{client.age} years</dd>
                </div>
                <div>
                  <dt>Plan ID</dt>
                  <dd>{client.plan.id}</dd>
                </div>
              </dl>

              <div className="profile-plan">
                <div>
                  <span>Treatment goal</span>
                  <p>{client.plan.goal}</p>
                </div>
                <div>
                  <span>Current objective</span>
                  <p>{client.plan.objective}</p>
                </div>
              </div>

              <div className="profile-sync">
                <RefreshCw size={16} aria-hidden="true" />
                <span>
                  <strong>Record source</strong>
                  <small>
                    {client.id.startsWith('local-')
                      ? 'Saved only in this browser'
                      : `Last synchronized ${client.plan.lastSynced}`}
                  </small>
                </span>
              </div>
            </div>
          </section>
        </div>
      )}

      {showHelpModal && (
        <div className="modal-backdrop" role="presentation">
          <section
            className="client-modal help-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="help-modal-title"
          >
            <div className="modal-header">
              <div>
                <p className="section-kicker">Workspace guide</p>
                <h2 id="help-modal-title">Help and support</h2>
              </div>
              <button
                className="close-button"
                type="button"
                aria-label="Close help and support"
                onClick={() => setShowHelpModal(false)}
              >
                <X size={20} />
              </button>
            </div>

            <div className="help-modal-body">
              <div className="help-grid">
                <article>
                  <FileCheck2 size={20} aria-hidden="true" />
                  <h3>Start a test workflow</h3>
                  <p>
                    Select an active client or use the plus button to create a fictional record in
                    this browser.
                  </p>
                </article>
                <article>
                  <Mic2 size={20} aria-hidden="true" />
                  <h3>Use live voice</h3>
                  <p>
                    Choose Voice summary, allow microphone access, speak six complete facts, then
                    review the mapped fields.
                  </p>
                </article>
                <article>
                  <ShieldCheck size={20} aria-hidden="true" />
                  <h3>Review before completion</h3>
                  <p>
                    Edit every generated draft, confirm the review checkbox, and approve only when
                    the content is accurate.
                  </p>
                </article>
              </div>
              <div className="support-boundary">
                <AlertTriangle size={18} aria-hidden="true" />
                <p>
                  This public site is for fictional demonstrations only. It does not provide
                  clinical or emergency support and must not receive real patient information.
                </p>
              </div>
              <a
                className="primary-button help-link"
                href="https://github.com/manideepe/clinical-documentation-copilot#project-guide"
                target="_blank"
                rel="noreferrer"
              >
                Open project guide
              </a>
            </div>
          </section>
        </div>
      )}

      {showClientModal && (
        <div className="modal-backdrop" role="presentation">
          <section
            className="client-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="client-modal-title"
          >
            <div className="modal-header">
              <div>
                <p className="section-kicker">Browser-local test record</p>
                <h2 id="client-modal-title">Create a test client</h2>
              </div>
              <button
                className="close-button"
                type="button"
                aria-label="Close create client dialog"
                onClick={() => setShowClientModal(false)}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={addLocalClient}>
              <div className="privacy-notice" role="note">
                <ShieldCheck size={19} aria-hidden="true" />
                <div>
                  <strong>Use fictional information only</strong>
                  <p>
                    Do not enter real patient information. This test record stays in this browser
                    and is not shared with other visitors.
                  </p>
                </div>
              </div>

              <div className="client-form-grid">
                <label>
                  Full name
                  <input
                    required
                    value={clientDraft.name}
                    onChange={(event) => updateClientDraft('name', event.target.value)}
                    placeholder="Example: Taylor Brooks"
                  />
                </label>
                <label>
                  Preferred name
                  <input
                    value={clientDraft.preferredName}
                    onChange={(event) => updateClientDraft('preferredName', event.target.value)}
                    placeholder="Taylor"
                  />
                </label>
                <label>
                  Pronouns
                  <select
                    value={clientDraft.pronouns}
                    onChange={(event) => updateClientDraft('pronouns', event.target.value)}
                  >
                    <option>they/them</option>
                    <option>she/her</option>
                    <option>he/him</option>
                    <option>not supplied</option>
                  </select>
                </label>
                <label>
                  Date of birth
                  <input
                    required
                    type="date"
                    value={clientDraft.dateOfBirth}
                    onChange={(event) => updateClientDraft('dateOfBirth', event.target.value)}
                  />
                </label>
                <label>
                  Test record ID
                  <input
                    required
                    value={clientDraft.ehrId}
                    onChange={(event) => updateClientDraft('ehrId', event.target.value)}
                    placeholder="TEST-1001"
                  />
                </label>
                <label>
                  Plan ID
                  <input
                    required
                    value={clientDraft.planId}
                    onChange={(event) => updateClientDraft('planId', event.target.value)}
                    placeholder="PLAN-1001"
                  />
                </label>
                <label>
                  Effective date
                  <input
                    required
                    type="date"
                    value={clientDraft.effectiveDate}
                    onChange={(event) => updateClientDraft('effectiveDate', event.target.value)}
                  />
                </label>
                <label>
                  Review date
                  <input
                    required
                    type="date"
                    value={clientDraft.endDate}
                    onChange={(event) => updateClientDraft('endDate', event.target.value)}
                  />
                </label>
                <label className="full-width">
                  Treatment goal
                  <textarea
                    required
                    rows={2}
                    value={clientDraft.goal}
                    onChange={(event) => updateClientDraft('goal', event.target.value)}
                    placeholder="Enter a fictional treatment goal for the demo."
                  />
                </label>
                <label className="full-width">
                  Treatment objective
                  <textarea
                    required
                    rows={2}
                    value={clientDraft.objective}
                    onChange={(event) => updateClientDraft('objective', event.target.value)}
                    placeholder="Enter a measurable fictional objective."
                  />
                </label>
              </div>

              <div className="modal-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setShowClientModal(false)}
                >
                  Cancel
                </button>
                <button className="primary-button" type="submit">
                  <Plus size={17} />
                  Create test client
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}

export default App
