import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

async function renderWorkspace() {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole('heading', { name: 'Appointment workspace' })
  return user
}

describe('clinical documentation workspace', () => {
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

    await new Promise((resolve) => window.setTimeout(resolve, 750))
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
})
