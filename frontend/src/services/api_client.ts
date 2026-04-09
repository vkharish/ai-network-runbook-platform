// Typed API client for the AI Network Runbook Platform backend

const API_BASE = import.meta.env.VITE_API_URL ?? '/api/v1'

// ── Types ──────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
}

export interface Device {
  id: string
  hostname: string
  display_name: string
  vendor: string
  os: string
  device_type: string
  live_enabled: boolean
  has_credentials: boolean
}

export interface Incident {
  id: string
  incident_number: number | null
  title: string
  description: string
  severity: string
  status: string
  affected_device: string | null
  affected_protocol: string | null
  root_cause: string | null
  ai_report: AIReport | null
  created_at: string
  updated_at: string
}

export interface AIReport {
  summary: string
  root_cause: string
  hypothesis: string
  confidence: number
  urgency: string
  steps: string[]
  commands: string[]
  citations: Citation[]
  affected_components: string[]
  escalation: string
  generated_at: string
  llm_provider: string
  orchestration: Orchestration
}

export interface Citation {
  source: string
  chunk_index: number
  score: number
}

export interface Orchestration {
  decisions: string[]
  agents_invoked: string[]
  total_iterations: number
}

export interface Runbook {
  id: string
  title: string
  filename: string
  status: string
  chunk_count: number
  tags: string[]
  created_at: string
}

export interface RAGResult {
  text: string
  source: string
  score: number
  chunk_index: number
}

export interface RAGQueryResponse {
  answer: string
  results: RAGResult[]
  query: string
}

// ── Token storage ──────────────────────────────────────────────────────────

export const getToken = () => localStorage.getItem('access_token') ?? ''
export const setToken = (t: string) => localStorage.setItem('access_token', t)
export const clearToken = () => localStorage.removeItem('access_token')

// ── Core fetch helper ──────────────────────────────────────────────────────

async function authFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const t = token ?? getToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(t ? { Authorization: `Bearer ${t}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  const text = await res.text()
  if (text.trimStart().startsWith('<')) {
    throw new Error('Backend unreachable — is the API server running on port 8000?')
  }
  return JSON.parse(text) as T
}

// ── Auth ───────────────────────────────────────────────────────────────────

export async function login(email: string, password: string) {
  const data = await authFetch<{ access_token: string; refresh_token: string }>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
    '',
  )
  setToken(data.access_token)
  return data
}

export async function getMe(): Promise<User> {
  return authFetch<User>('/auth/me')
}

export function logout() {
  clearToken()
}

// ── Incidents ──────────────────────────────────────────────────────────────

export async function listIncidents(statusFilter?: string): Promise<Incident[]> {
  const qs = statusFilter ? `?status_filter=${statusFilter}` : ''
  return authFetch<Incident[]>(`/incidents/${qs}`)
}

export async function getIncident(id: string): Promise<Incident> {
  return authFetch<Incident>(`/incidents/${id}`)
}

export async function createIncident(payload: {
  title: string
  description: string
  severity: string
  affected_device?: string
  affected_protocol?: string
}): Promise<Incident> {
  return authFetch<Incident>('/incidents/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function triggerDiagnosis(id: string): Promise<Incident> {
  return authFetch<Incident>(`/incidents/${id}/diagnose`, { method: 'POST' })
}

export async function updateIncidentStatus(id: string, status: string): Promise<Incident> {
  return authFetch<Incident>(`/incidents/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export async function deleteIncident(id: string): Promise<void> {
  await authFetch<void>(`/incidents/${id}`, { method: 'DELETE' })
}

// ── Devices ────────────────────────────────────────────────────────────────

export async function listDevices(): Promise<Device[]> {
  return authFetch<Device[]>('/devices/')
}

// ── Runbooks ───────────────────────────────────────────────────────────────

export async function listRunbooks(): Promise<Runbook[]> {
  return authFetch<Runbook[]>('/runbooks/')
}

export async function queryRunbooks(
  query: string,
  topK = 5,
  filterTags?: string[],
): Promise<RAGQueryResponse> {
  return authFetch<RAGQueryResponse>('/runbooks/query', {
    method: 'POST',
    body: JSON.stringify({ query, top_k: topK, filter_tags: filterTags }),
  })
}

export async function uploadRunbook(file: File, title: string, tags: string[]): Promise<Runbook> {
  const form = new FormData()
  form.append('file', file)
  form.append('title', title)
  form.append('tags', tags.join(','))
  const res = await fetch(`${API_BASE}/runbooks/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

// ── Topology ────────────────────────────────────────────────────────────────

export interface TopologyDevice {
  id: string
  hostname: string
  vendor: string
  os: string
  role: string
  model: string
  loopback: string
  protocols: Record<string, unknown>
}

export interface TopologyEdge {
  source: string
  target: string
  local_iface: string
  remote_iface: string
  local_ip?: string
  status: string
}

export interface TopologyRecord {
  id: string
  name: string
  description: string | null
  status: string
  is_default: boolean
  graph_data: {
    name: string
    nodes: TopologyDevice[]
    edges: TopologyEdge[]
    failure_scenarios: Record<string, unknown>
  } | null
  created_at: string
}

export interface SimulateResponse {
  failure_report: {
    scenario: string
    type: string
    affected_device: string
    affected_interface?: string
    changes: string[]
    success: boolean
  }
  impact_analysis: {
    failed_device: string
    failed_hostname: string
    isolated_devices: { id: string; hostname: string; role: string }[]
    impact_count: number
    core_devices: string[]
  }
  available_scenarios: string[]
  post_failure_graph: Record<string, unknown>
}

export async function listTopologies(): Promise<TopologyRecord[]> {
  return authFetch<TopologyRecord[]>('/topology/')
}

export async function simulateFailure(topologyId: string, scenarioName: string): Promise<SimulateResponse> {
  return authFetch<SimulateResponse>(`/topology/${topologyId}/simulate`, {
    method: 'POST',
    body: JSON.stringify({ scenario_name: scenarioName }),
  })
}
