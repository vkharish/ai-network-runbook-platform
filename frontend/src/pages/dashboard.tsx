import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listIncidents, createIncident, logout, Incident } from '../services/api_client'
import IncidentCard from '../components/IncidentCard'

const STATUSES = ['open', 'diagnosing', 'awaiting_input', 'resolved', 'closed']

function statusCount(incidents: Incident[], status: string) {
  return incidents.filter(i => i.status === status).length
}

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading]     = useState(true)
  const [showForm, setShowForm]   = useState(false)
  const [filter, setFilter]       = useState('')
  const navigate = useNavigate()

  const [form, setForm] = useState({
    title: '', description: '', severity: 'P2',
    affected_device: '', affected_protocol: '',
  })

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

  useEffect(() => { load() }, [filter])

  // Auto-refresh every 30 s
  useEffect(() => {
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [filter])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    try {
      await createIncident({
        ...form,
        affected_device: form.affected_device || undefined,
        affected_protocol: form.affected_protocol || undefined,
      } as any)
      setShowForm(false)
      setForm({ title: '', description: '', severity: 'P2', affected_device: '', affected_protocol: '' })
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
        </div>
        <button onClick={handleLogout} className="text-xs text-gray-400 hover:text-white">Sign out</button>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* Status summary */}
        <div className="grid grid-cols-5 gap-3 mb-6">
          {STATUSES.map(s => (
            <button
              key={s}
              onClick={() => setFilter(filter === s ? '' : s)}
              className={`rounded-lg p-3 text-center border transition ${filter === s ? 'border-blue-500 bg-blue-50' : 'bg-white border-gray-200 hover:border-blue-300'}`}
            >
              <p className="text-2xl font-bold text-gray-800">{statusCount(incidents, s)}</p>
              <p className="text-xs text-gray-500 mt-0.5 capitalize">{s.replace('_', ' ')}</p>
            </button>
          ))}
        </div>

        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">
            Incidents {filter && <span className="text-sm text-gray-500">({filter})</span>}
          </h2>
          <button
            onClick={() => setShowForm(true)}
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
              <form onSubmit={handleCreate} className="space-y-3">
                <input required placeholder="Title" value={form.title}
                  onChange={e => setForm({...form, title: e.target.value})}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
                <textarea required placeholder="Description" value={form.description}
                  onChange={e => setForm({...form, description: e.target.value})}
                  rows={3} className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
                <div className="grid grid-cols-3 gap-2">
                  <select value={form.severity}
                    onChange={e => setForm({...form, severity: e.target.value})}
                    className="border border-gray-300 rounded px-3 py-2 text-sm">
                    {['P1','P2','P3','P4'].map(s => <option key={s}>{s}</option>)}
                  </select>
                  <input placeholder="Affected device" value={form.affected_device}
                    onChange={e => setForm({...form, affected_device: e.target.value})}
                    className="border border-gray-300 rounded px-3 py-2 text-sm" />
                  <input placeholder="Protocol (bgp/ospf)" value={form.affected_protocol}
                    onChange={e => setForm({...form, affected_protocol: e.target.value})}
                    className="border border-gray-300 rounded px-3 py-2 text-sm" />
                </div>
                <div className="flex gap-2 justify-end">
                  <button type="button" onClick={() => setShowForm(false)}
                    className="text-sm text-gray-500 hover:text-gray-700 px-4 py-2">Cancel</button>
                  <button type="submit"
                    className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg">
                    Create
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
