import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getIncident, triggerDiagnosis, Incident } from '../services/api_client'
import DiagnosisReport from '../components/DiagnosisReport'

export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [incident, setIncident] = useState<Incident | null>(null)
  const [loading, setLoading]   = useState(true)
  const [diagnosing, setDiaGnosing] = useState(false)
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
    setDiaGnosing(true)
    try {
      await triggerDiagnosis(id)
      await load()
    } catch (err: any) {
      alert(err.message)
    } finally {
      setDiaGnosing(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-screen text-gray-400">Loading…</div>
  if (!incident) return null

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-gray-900 text-white px-6 py-3 flex items-center gap-4">
        <button onClick={() => navigate('/dashboard')} className="text-xs text-gray-400 hover:text-white">
          ← Dashboard
        </button>
        <span className="text-sm font-semibold">{incident.title}</span>
      </nav>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {/* Incident header */}
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-bold bg-gray-100 px-2 py-0.5 rounded">{incident.severity}</span>
                <span className="text-xs text-gray-500 capitalize">{incident.status.replace('_', ' ')}</span>
              </div>
              <h1 className="text-lg font-bold text-gray-800">{incident.title}</h1>
              <p className="text-sm text-gray-600 mt-1">{incident.description}</p>
              <div className="flex gap-4 mt-3 text-xs text-gray-400">
                {incident.affected_device && <span>Device: <strong>{incident.affected_device}</strong></span>}
                {incident.affected_protocol && <span>Protocol: <strong>{incident.affected_protocol.toUpperCase()}</strong></span>}
                <span>Created: {new Date(incident.created_at).toLocaleString()}</span>
              </div>
            </div>

            {(incident.status === 'open' || incident.status === 'awaiting_input') && (
              <button
                onClick={handleDiagnose}
                disabled={diagnosing}
                className="shrink-0 bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50"
              >
                {diagnosing ? 'Triggering…' : 'Run Diagnosis'}
              </button>
            )}
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
            <h2 className="text-base font-semibold text-gray-700 mb-3">AI Diagnosis Report</h2>
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
