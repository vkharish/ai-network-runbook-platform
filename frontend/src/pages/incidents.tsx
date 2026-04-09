import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getIncident, triggerDiagnosis, updateIncidentStatus, deleteIncident, Incident } from '../services/api_client'
import DiagnosisReport from '../components/DiagnosisReport'

const STATUS_COLORS: Record<string, string> = {
  open:           'bg-blue-100 text-blue-700',
  diagnosing:     'bg-purple-100 text-purple-700',
  awaiting_input: 'bg-yellow-100 text-yellow-700',
  resolved:       'bg-green-100 text-green-700',
  closed:         'bg-gray-100 text-gray-500',
}

export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [incident, setIncident] = useState<Incident | null>(null)
  const [loading, setLoading]   = useState(true)
  const [diagnosing, setDiagnosing] = useState(false)
  const [updating, setUpdating] = useState(false)
  const navigate = useNavigate()

  async function load() {
    if (!id) return
    try {
      const data = await getIncident(id)
      setIncident(data)
    } catch {
      navigate('/dashboard')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  // Poll every 5 s while diagnosing
  useEffect(() => {
    if (incident?.status !== 'diagnosing') return
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [incident?.status])

  async function handleDiagnose() {
    if (!id) return
    setDiagnosing(true)
    try {
      await triggerDiagnosis(id)
      await load()
    } catch (err: any) {
      alert(err.message)
    } finally {
      setDiagnosing(false)
    }
  }

  async function handleStatusChange(newStatus: string) {
    if (!id) return
    setUpdating(true)
    try {
      await updateIncidentStatus(id, newStatus)
      await load()
    } catch (err: any) {
      alert(err.message)
    } finally {
      setUpdating(false)
    }
  }

  async function handleDelete() {
    if (!id || !confirm('Delete this incident? This cannot be undone.')) return
    try {
      await deleteIncident(id)
      navigate('/dashboard')
    } catch (err: any) {
      alert(err.message)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-screen text-gray-400">Loading…</div>
  if (!incident) return null

  const statusClass = STATUS_COLORS[incident.status] ?? 'bg-gray-100 text-gray-600'
  const canDiagnose = ['open', 'awaiting_input', 'resolved'].includes(incident.status)

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-gray-900 text-white px-6 py-3 flex items-center gap-4">
        <button onClick={() => navigate('/dashboard')} className="text-xs text-gray-400 hover:text-white">
          ← Dashboard
        </button>
        {incident.incident_number != null && (
          <span className="text-xs font-mono text-gray-400">
            INC-{String(incident.incident_number).padStart(4, '0')}
          </span>
        )}
        <span className="text-sm font-semibold">{incident.title}</span>
      </nav>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {/* Incident header */}
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-bold bg-gray-100 px-2 py-0.5 rounded">{incident.severity}</span>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full capitalize ${statusClass}`}>
                  {incident.status.replace('_', ' ')}
                </span>
              </div>
              <h1 className="text-lg font-bold text-gray-800">{incident.title}</h1>
              <p className="text-sm text-gray-600 mt-1">{incident.description}</p>
              <div className="flex gap-4 mt-3 text-xs text-gray-400">
                {incident.affected_device && <span>Device: <strong>{incident.affected_device}</strong></span>}
                {incident.affected_protocol && <span>Protocol: <strong>{incident.affected_protocol.toUpperCase()}</strong></span>}
                <span>Created: {new Date(incident.created_at).toLocaleString()}</span>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex flex-col gap-2 shrink-0">
              {canDiagnose && (
                <button
                  onClick={handleDiagnose}
                  disabled={diagnosing || updating}
                  className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50"
                >
                  {diagnosing ? 'Triggering…' : incident.status === 'resolved' ? 'Re-run Diagnosis' : 'Run Diagnosis'}
                </button>
              )}
              {incident.status === 'awaiting_input' && (
                <button
                  onClick={() => handleStatusChange('resolved')}
                  disabled={updating}
                  className="bg-green-600 hover:bg-green-700 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50"
                >
                  {updating ? 'Saving…' : 'Mark Resolved'}
                </button>
              )}
              {incident.status === 'resolved' && (
                <button
                  onClick={() => handleStatusChange('closed')}
                  disabled={updating}
                  className="bg-gray-600 hover:bg-gray-700 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50"
                >
                  {updating ? 'Saving…' : 'Close Incident'}
                </button>
              )}
              {incident.status === 'closed' && (
                <button
                  onClick={() => handleStatusChange('open')}
                  disabled={updating}
                  className="border border-gray-300 hover:bg-gray-50 text-gray-600 text-sm px-4 py-2 rounded-lg disabled:opacity-50"
                >
                  Reopen
                </button>
              )}
              <button
                onClick={handleDelete}
                className="border border-red-200 hover:bg-red-50 text-red-500 text-sm px-4 py-2 rounded-lg"
              >
                Delete
              </button>
            </div>
          </div>

          {incident.status === 'diagnosing' && (
            <div className="mt-4 flex items-center gap-2 text-sm text-purple-600 bg-purple-50 px-3 py-2 rounded">
              <span className="animate-spin">⟳</span>
              AI diagnosis in progress… auto-refreshing
            </div>
          )}
        </div>

        {/* AI Report */}
        {incident.ai_report ? (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-semibold text-gray-700">AI Diagnosis Report</h2>
              {incident.ai_report.llm_provider && (
                <span className="text-xs bg-purple-50 text-purple-700 border border-purple-200 px-2 py-0.5 rounded-full font-mono">
                  {incident.ai_report.llm_provider}
                </span>
              )}
            </div>
            <DiagnosisReport report={incident.ai_report} />
          </div>
        ) : incident.status !== 'diagnosing' && (
          <div className="text-center py-8 text-gray-400 text-sm">
            No diagnosis report yet. Click "Run Diagnosis" to start.
          </div>
        )}
      </div>
    </div>
  )
}
