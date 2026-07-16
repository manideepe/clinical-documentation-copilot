import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach } from 'vitest'
import App from './App'

async function renderWorkspace() {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole('heading', { name: 'Appointment workspace' })
  return user
}

describe('clinical documentation workspace', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('offers all eight organization note types', async () => {
    await renderWorkspace()

    const noteTypeSelect = screen.getByLabelText('Note type')
    const options = within(noteTypeSelect).getAllByRole('option')

    expect(options).toHaveLength(8)
    expect(options.map((option) => option.textContent)).toEqual([
      'Case Management Note',
      'Initial Child Assessment',
      'Child Assessment Update',
      'Initial Adult Assessment',
      'Adult Assessment Update',
      'Counselor Note',
      'Evaluation and Management (E&M) Note',
      'Nursing Progress Note',
    ])
  })

  it('blocks voice and generation for an expired treatment plan while allowing facts to save', async () => {
    const user = await renderWorkspace()

    const clientSearch = screen.getByLabelText('Client')
    await user.click(clientSearch)
    await user.click(await screen.findByRole('option', { name: /Jordan Lee/i }))

    expect(screen.getByRole('alert')).toHaveTextContent('Treatment plan expired')
    expect(screen.getByRole('button', { name: /Voice summary/i })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Generate clinical note/i })).not.toBeInTheDocument()

    const saveButton = screen.getByRole('button', { name: 'Save session facts' })
    expect(saveButton).toBeEnabled()
    await user.click(saveButton)

    expect(screen.getByText('Facts saved')).toBeInTheDocument()
    expect(screen.getByText('7 source facts preserved · just now')).toBeInTheDocument()
  })

  it('requires clinician review before approval and copy', async () => {
    const user = await renderWorkspace()

    expect(screen.queryByRole('button', { name: 'Approve note' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Generate clinical note' }))
    const approveButton = await screen.findByRole('button', { name: 'Approve note' })
    const copyButton = screen.getByRole('button', { name: 'Copy note' })
    expect(approveButton).toBeDisabled()
    expect(copyButton).toBeDisabled()

    await user.click(screen.getByLabelText(/I reviewed this entire note/i))
    expect(approveButton).toBeEnabled()
    await user.click(approveButton)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Approved' })).toBeDisabled())
    expect(copyButton).toBeEnabled()
  })

  it('invalidates a draft when source facts or note type change', async () => {
    const user = await renderWorkspace()
    await user.click(screen.getByRole('button', { name: 'Generate clinical note' }))
    await screen.findByLabelText('Edit note content')

    const topics = screen.getByLabelText(/Topics discussed/i)
    await user.clear(topics)
    await user.type(topics, 'A revised synthetic session topic.')
    expect(screen.queryByLabelText('Edit note content')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Generate clinical note' }))
    await screen.findByLabelText('Edit note content')
    await user.selectOptions(screen.getByLabelText('Note type'), 'Nursing Progress Note')
    expect(screen.queryByLabelText('Edit note content')).not.toBeInTheDocument()
  })

  it('does not carry edited facts from one client into another client', async () => {
    const user = await renderWorkspace()
    const topics = screen.getByLabelText(/Topics discussed/i)
    await user.clear(topics)
    await user.type(topics, 'Client-specific synthetic text that must not cross records.')

    await user.click(screen.getByLabelText('Client'))
    await user.click(await screen.findByRole('option', { name: /Jordan Lee/i }))
    expect(screen.getByLabelText(/Topics discussed/i)).toHaveValue(
      'Reviewed anxiety triggers at work and recent changes to sleep routine.',
    )
  })

  it('cancels an in-flight draft when the selected client changes', async () => {
    const user = await renderWorkspace()
    await user.click(screen.getByRole('button', { name: 'Generate clinical note' }))
    await user.click(screen.getByLabelText('Client'))
    await user.click(await screen.findByRole('option', { name: /Jordan Lee/i }))

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 750))
    })
    expect(screen.queryByText('Clinical draft generated')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Edit note content')).not.toBeInTheDocument()
  })

  it('uses appointment details in the draft and invalidates it when they change', async () => {
    const user = await renderWorkspace()
    await user.selectOptions(screen.getByLabelText('Service type'), 'Case Management · 45 min')
    await user.click(screen.getByRole('button', { name: 'Generate clinical note' }))
    const editor = await screen.findByLabelText('Edit note content')
    expect((editor as HTMLTextAreaElement).value).toContain('Service: Case Management · 45 min')

    await user.selectOptions(screen.getByLabelText('Staff member'), 'Michael Ortiz, RN')
    expect(screen.queryByLabelText('Edit note content')).not.toBeInTheDocument()
  })

  it('creates and persists a browser-local test client with empty session facts', async () => {
    const user = await renderWorkspace()

    await user.click(screen.getByRole('button', { name: 'Add client' }))
    expect(screen.getByRole('dialog', { name: 'Create a test client' })).toBeInTheDocument()
    expect(screen.getByText('Use fictional information only')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Full name'), 'Taylor Brooks')
    await user.type(screen.getByLabelText('Test record ID'), 'TEST-1001')
    await user.type(screen.getByLabelText('Plan ID'), 'PLAN-1001')
    await user.type(
      screen.getByLabelText('Treatment goal'),
      'Improve consistent use of coping skills.',
    )
    await user.type(
      screen.getByLabelText('Treatment objective'),
      'Practice one coping strategy on four days each week.',
    )
    await user.click(screen.getByRole('button', { name: 'Create test client' }))

    expect(screen.getByRole('heading', { name: 'Taylor Brooks' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Topics discussed/i)).toHaveValue('')
    expect(localStorage.getItem('claritynote-local-test-clients-v1')).toContain('Taylor Brooks')
  })

  it('maps a voice transcript into structured facts for clinician review', async () => {
    const user = await renderWorkspace()

    await user.click(screen.getByRole('button', { name: /Voice summary/i }))
    const transcript = screen.getByLabelText('Live transcript')
    await user.type(
      transcript,
      'Discussed work stress. Provided coping skills coaching. Client practiced grounding. Client reported progress this week. Modeled paced breathing. No acute concerns reported. Continue daily practice before the next visit.',
    )
    await user.click(screen.getByRole('button', { name: 'Use transcript in session facts' }))

    expect(screen.getByRole('button', { name: /Text summary/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByLabelText(/Topics discussed/i)).toHaveValue('Discussed work stress.')
    expect(screen.getByLabelText(/Concerns or barriers/i)).toHaveValue(
      'No acute concerns reported.',
    )
    expect(screen.getByLabelText(/Goals and next steps/i)).toHaveValue(
      'Continue daily practice before the next visit.',
    )
  })

  it('opens client details, logs a supervisor alert, and provides help guidance', async () => {
    const user = await renderWorkspace()

    await user.click(screen.getByRole('button', { name: 'View client profile' }))
    const profile = screen.getByRole('dialog', { name: 'Avery Morgan' })
    expect(within(profile).getByText('EHR-28419')).toBeInTheDocument()
    expect(within(profile).getByText('TP-2026-0419')).toBeInTheDocument()
    await user.click(within(profile).getByRole('button', { name: 'Close client profile' }))

    await user.click(screen.getByLabelText('Client'))
    await user.click(await screen.findByRole('option', { name: /Jordan Lee/i }))
    await user.click(screen.getByRole('button', { name: 'Notify supervisor' }))
    expect(screen.getByRole('button', { name: 'Supervisor alert logged' })).toBeDisabled()
    expect(screen.getByText('A local workflow alert was added for the expired treatment plan.'))
      .toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Help and support' }))
    const help = screen.getByRole('dialog', { name: 'Help and support' })
    expect(within(help).getByText('Use live voice')).toBeInTheDocument()
    expect(within(help).getByRole('link', { name: 'Open project guide' })).toHaveAttribute(
      'href',
      expect.stringContaining('github.com/manideepe/clinical-documentation-copilot'),
    )
  })
})
