import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listIncidents, createIncident, listDevices, logout, Incident, Device } from '../services/api_client'
import IncidentCard from '../components/IncidentCard'

const STATUSES = ['open', 'diagnosing', 'awaiting_input', 'resolved', 'closed']

const STATUS_COLORS: Record<string, string> = {
  open:           'border-blue-300 bg-blue-50 text-blue-700',
  diagnosing:     'border-purple-300 bg-purple-50 text-purple-700',
  awaiting_input: 'border-yellow-300 bg-yellow-50 text-yellow-700',
  resolved:       'border-green-300 bg-green-50 text-green-700',
  closed:         'border-gray-200 bg-gray-50 text-gray-400',
}
const PROTOCOLS = ['BGP', 'OSPF', 'Interface', 'MPLS', 'ISIS', 'EIGRP', 'STP', 'LACP']

function statusCount(incidents: Incident[], status: string) {
  return incidents.filter(i => i.status === status).length
}

function deviceDot(d: Device) {
  if (d.live_enabled) return '🔴'
  if (d.vendor?.toLowerCase().includes('juniper') || d.os?.toLowerCase().includes('junos')) return '🟠'
  return '🟡'
}

const EMPTY_FORM = {
  title: '', description: '', severity: 'P2',
  affected_device: '', protocols: [] as string[],
}

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading]     = useState(true)
  const [showForm, setShowForm]   = useState(false)
  const [filter, setFilter]       = useState('')
  const [devices, setDevices]     = useState<Device[]>([])
  const [form, setForm]           = useState(EMPTY_FORM)
  const navigate = useNavigate()

  async function load() {
    try {
      const data = await listIncidents(filter || undefined)
      setIncidents(data)
    } catch {
      navigate('/login')
    } finally {
      setLoading(false)
    }
  }

  async function openForm() {
    setShowForm(true)
    try {
      const devs = await listDevices()
      setDevices(devs)
    } catch {
      // silently ignore — device dropdown will be empty
    }
  }

  useEffect(() => { load() }, [filter])

  // Auto-refresh every 30 s
  useEffect(() => {
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [filter])

  function toggleProtocol(p: string) {
    setForm(f => ({
      ...f,
      protocols: f.protocols.includes(p)
        ? f.protocols.filter(x => x !== p)
        : [...f.protocols, p],
    }))
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    try {
      await createIncident({
        title: form.title,
        description: form.description,
        severity: form.severity,
        affected_device: form.affected_device || undefined,
        affected_protocol: form.protocols.length > 0 ? form.protocols.join(',') : undefined,
      })
      setShowForm(false)
      setForm(EMPTY_FORM)
      load()
    } catch (err: any) {
      alert(err.message)
    }
  }

  function handleLogout() { logout(); navigate('/login') }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav */}
      <nav className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="font-bold text-sm">AI Runbook Platform</span>
          <button onClick={() => navigate('/dashboard')} className="text-xs text-gray-300 hover:text-white">Dashboard</button>
          <button onClick={() => navigate('/runbooks')} className="text-xs text-gray-300 hover:text-white">Runbooks</button>
          <button onClick={() => navigate('/topology')} className="text-xs text-gray-300 hover:text-white">Topology</button>
        </div>
        <button onClick={handleLogout} className="text-xs text-gray-400 hover:text-white">Sign out</button>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* Status summary */}
        <div className="grid grid-cols-5 gap-3 mb-6">
          {STATUSES.map(s => {
            const active = filter === s
            const colorClass = active ? STATUS_COLORS[s] : 'bg-white border-gray-200 hover:border-blue-300'
            return (
              <button
                key={s}
                onClick={() => setFilter(active ? '' : s)}
                className={`rounded-lg p-3 text-center border transition ${colorClass}`}
              >
                <p className="text-2xl font-bold">{statusCount(incidents, s)}</p>
                <p className="text-xs mt-0.5 capitalize">{s.replace('_', ' ')}</p>
              </button>
            )
          })}
        </div>

        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">
            Incidents {filter && <span className="text-sm text-gray-500">({filter})</span>}
          </h2>
          <button
            onClick={openForm}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg"
          >
            + New Incident
          </button>
        </div>

        {/* Create form modal */}
        {showForm && (
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
              <h3 className="font-semibold text-gray-800 mb-4">New Incident</h3>
              <form onSubmit={handleCreate} className="space-y-4">

                {/* Title */}
                <input required placeholder="Title" value={form.title}
                  onChange={e => setForm({...form, title: e.target.value})}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />

                {/* Description */}
                <textarea required placeholder="Description" value={form.description}
                  onChange={e => setForm({...form, description: e.target.value})}
                  rows={2} className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />

                {/* Affected Device dropdown */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Affected Device</label>
                  <select
                    value={form.affected_device}
                    onChange={e => setForm({...form, affected_device: e.target.value})}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm bg-white"
                  >
                    <option value="">— select device —</option>
                    {devices.map(d => (
                      <option key={d.id} value={d.hostname}>
                        {deviceDot(d)} {d.hostname}
                        {d.display_name ? ` (${d.display_name})` : ''}
                        {' '}· {d.vendor} {d.os}
                        {d.live_enabled ? ' · live' : ' · sim'}
                      </option>
                    ))}
                  </select>
                  {devices.length === 0 && (
                    <p className="text-xs text-gray-400 mt-1">No devices registered — or still loading</p>
                  )}
                </div>

                {/* Protocol multi-select chips */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-2">Affected Protocol</label>
                  <div className="flex flex-wrap gap-2">
                    {PROTOCOLS.map(p => {
                      const active = form.protocols.includes(p)
                      return (
                        <button
                          key={p}
                          type="button"
                          onClick={() => toggleProtocol(p)}
                          className={`text-xs px-3 py-1 rounded-full border font-medium transition ${
                            active
                              ? 'bg-blue-600 text-white border-blue-600'
                              : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                          }`}
                        >
                          {p}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Severity */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Severity</label>
                  <select value={form.severity}
                    onChange={e => setForm({...form, severity: e.target.value})}
                    className="border border-gray-300 rounded px-3 py-2 text-sm bg-white">
                    {['P1','P2','P3','P4'].map(s => <option key={s}>{s}</option>)}
                  </select>
                </div>

                <div className="flex gap-2 justify-end pt-1">
                  <button type="button" onClick={() => setShowForm(false)}
                    className="text-sm text-gray-500 hover:text-gray-700 px-4 py-2">Cancel</button>
                  <button type="submit"
                    className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg">
                    Create &amp; Diagnose
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Incident list */}
        {loading ? (
          <p className="text-center text-gray-400 py-12">Loading…</p>
        ) : incidents.length === 0 ? (
          <p className="text-center text-gray-400 py-12">No incidents found.</p>
        ) : (
          <div className="space-y-3">
            {incidents.map(inc => (
              <IncidentCard key={inc.id} incident={inc} onRefresh={load} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
