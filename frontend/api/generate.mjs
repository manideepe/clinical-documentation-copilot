const MODEL = 'gpt-oss:20b'
const MAX_BODY_BYTES = 20_000
const REQUEST_LIMIT = 10
const WINDOW_MS = 5 * 60 * 1000
const requestWindows = new Map()

function send(response, status, body) {
  response.setHeader('Cache-Control', 'no-store')
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.status(status).json(body)
}

function getRequestAddress(request) {
  const forwarded = request.headers['x-forwarded-for']
  if (typeof forwarded === 'string') return forwarded.split(',')[0].trim()
  return request.socket?.remoteAddress ?? 'unknown'
}

function isRateLimited(address) {
  const now = Date.now()
  const current = requestWindows.get(address)
  if (!current || now - current.startedAt >= WINDOW_MS) {
    requestWindows.set(address, { count: 1, startedAt: now })
    return false
  }
  current.count += 1
  return current.count > REQUEST_LIMIT
}

function isSameOrigin(request) {
  const origin = request.headers.origin
  if (!origin) return true
  const expectedHost = request.headers['x-forwarded-host'] ?? request.headers.host
  try {
    return new URL(origin).host === expectedHost
  } catch {
    return false
  }
}

function cleanText(value, maximumLength) {
  return typeof value === 'string' ? value.trim().slice(0, maximumLength) : ''
}

function normalizePayload(body) {
  const facts = Array.isArray(body?.facts)
    ? body.facts.slice(0, 7).map((fact) => ({
        label: cleanText(fact?.label, 80),
        value: cleanText(fact?.value, 1_200),
      }))
    : []

  return {
    appointmentDate: cleanText(body?.appointmentDate, 20),
    client: {
      ehrId: cleanText(body?.client?.ehrId, 80),
      name: cleanText(body?.client?.name, 120),
    },
    facts,
    noteType: cleanText(body?.noteType, 120),
    plan: {
      goal: cleanText(body?.plan?.goal, 1_200),
      objective: cleanText(body?.plan?.objective, 1_200),
    },
    serviceType: cleanText(body?.serviceType, 120),
    staffMember: cleanText(body?.staffMember, 120),
  }
}

function isValidPayload(payload) {
  const requiredText = [
    payload.appointmentDate,
    payload.client.ehrId,
    payload.client.name,
    payload.noteType,
    payload.plan.goal,
    payload.plan.objective,
    payload.serviceType,
    payload.staffMember,
  ]
  const completedFacts = payload.facts.filter((fact) => fact.label && fact.value)
  return requiredText.every(Boolean) && completedFacts.length >= 6
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST')
    return send(response, 405, { error: 'Method not allowed' })
  }
  if (!isSameOrigin(request)) return send(response, 403, { error: 'Origin rejected' })
  if (isRateLimited(getRequestAddress(request))) {
    return send(response, 429, { error: 'Demo generation limit reached. Try again shortly.' })
  }

  const bodyText = JSON.stringify(request.body ?? {})
  if (Buffer.byteLength(bodyText, 'utf8') > MAX_BODY_BYTES) {
    return send(response, 413, { error: 'Request is too large' })
  }

  const apiKey = process.env.OLLAMA_API_KEY
  if (!apiKey) return send(response, 503, { error: 'AI drafting is not configured' })

  const payload = normalizePayload(request.body)
  if (!isValidPayload(payload)) {
    return send(response, 400, { error: 'Six complete facts and all appointment fields are required' })
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 28_000)
  const startedAt = Date.now()

  try {
    const ollamaResponse = await fetch('https://ollama.com/api/chat', {
      method: 'POST',
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: MODEL,
        stream: false,
        think: false,
        options: {
          temperature: 0.1,
          num_predict: 900,
        },
        messages: [
          {
            role: 'system',
            content:
              'You draft concise clinical documentation from supplied fictional demo data. Use only facts explicitly supplied. Never add diagnoses, symptoms, quotations, risk findings, outcomes, dates, services, or observations that are absent. Preserve uncertainty. Return plain text only with exactly these headings: SESSION FOCUS, SERVICES AND INTERVENTIONS, CLIENT RESPONSE, PROGRESS TOWARD TREATMENT OBJECTIVE, BARRIERS / CONCERNS, PLAN. Do not include analysis, markdown fences, or a disclaimer.',
          },
          {
            role: 'user',
            content: JSON.stringify(payload),
          },
        ],
      }),
    })

    if (!ollamaResponse.ok) {
      return send(response, 502, { error: 'AI drafting is temporarily unavailable' })
    }

    const result = await ollamaResponse.json()
    const note = cleanText(result?.message?.content, 12_000)
    if (!note || !note.includes('SESSION FOCUS') || !note.includes('PLAN')) {
      return send(response, 502, { error: 'AI drafting returned an invalid response' })
    }

    return send(response, 200, {
      latencyMs: Date.now() - startedAt,
      model: MODEL,
      note,
    })
  } catch {
    return send(response, 504, { error: 'AI drafting timed out' })
  } finally {
    clearTimeout(timeout)
  }
}
