import { useEffect, useMemo, useRef, useState } from 'react'
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
} from 'lucide-react'
import { loadClients, type ClientRecord } from './api/client'

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
  const [appointmentDate, setAppointmentDate] = useState('2026-07-15')
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
  const [recording, setRecording] = useState(false)
  const [savedPending, setSavedPending] = useState(false)
  const [auditItems, setAuditItems] = useState(INITIAL_AUDIT)
  const generationToken = useRef(0)

  useEffect(() => {
    let mounted = true
    void loadClients().then((result) => {
      if (!mounted) return
      setClients(result.clients)
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

  function selectClient(clientId: string) {
    const nextClient = clients.find((item) => item.id === clientId)
    if (!nextClient) return

    generationToken.current += 1
    setSelectedClientId(clientId)
    setSearchTerm('')
    setShowClientResults(false)
    setMode('text')
    setReviewed(false)
    setApproved(false)
    setCopied(false)
    setCopyError(false)
    setGenerating(false)
    setSavedPending(false)
    setRecording(false)
    setStatus('In Progress')
    setFacts(INITIAL_FACTS)
    setAppointmentDate('2026-07-15')
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

  function invalidateDraft() {
    generationToken.current += 1
    setGenerating(false)
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
    setMode(nextMode)
    setRecording(false)
    invalidateDraft()
  }

  function generateNote() {
    if (!client || !canGenerate) return
    setGenerating(true)
    setReviewed(false)
    setApproved(false)
    setCopied(false)
    setCopyError(false)
    const requestToken = ++generationToken.current

    window.setTimeout(() => {
      if (generationToken.current !== requestToken) return
      setNote(
        buildGeneratedNote(
          client,
          noteType,
          facts,
          appointmentDate,
          staffMember,
          serviceType,
        ),
      )
      setGenerating(false)
      setStatus('Documentation Pending')
      setAuditItems((items) => [
        ...items.filter((item) => item.title !== 'Clinical draft generated'),
        {
          id: Date.now(),
          title: 'Clinical draft generated',
          detail: `${noteType} grounded in ${completedFacts} clinician facts.`,
          time: 'Just now',
          state: 'current',
        },
      ])
    }, 650)
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
            <button className="icon-button" type="button" aria-label="Add client">
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
            <button className="text-button" type="button">
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
              <button type="button" className="text-button warning">
                Notify supervisor
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
                  <small>{planIsActive ? 'Record at least 5 minutes' : 'Unavailable — plan expired'}</small>
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
                <div className={`mic-orb ${recording ? 'recording' : ''}`}>
                  <Mic2 size={26} aria-hidden="true" />
                </div>
                <h3>{recording ? 'Recording in progress' : 'Ready to capture voice summary'}</h3>
                <p>
                  Capture the clinician summary after the visit. A recording under 5:00 cannot be
                  used to generate a note.
                </p>
                <div className="recording-time">
                  <strong>{recording ? '00:12' : '00:00'}</strong>
                  <span>/ 05:00 minimum</span>
                </div>
                <button
                  type="button"
                  className={recording ? 'secondary-button danger' : 'primary-button'}
                  onClick={() => setRecording((current) => !current)}
                >
                  {recording ? 'Stop recording' : 'Start recording'}
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
                    <p>Current plan · 7 staff facts · appointment details · {noteType}</p>
                  </div>
                  <span>10 source fields supplied</span>
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
            <button type="button">Help and support</button>
          </footer>
        </main>
      </div>
    </div>
  )
}

export default App
