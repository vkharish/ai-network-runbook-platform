import { useNavigate } from 'react-router-dom'
import { Incident, triggerDiagnosis } from '../services/api_client'

const SEVERITY_COLORS: Record<string, string> = {
  P1: 'bg-red-100 text-red-700',
  P2: 'bg-orange-100 text-orange-700',
  P3: 'bg-yellow-100 text-yellow-700',
  P4: 'bg-green-100 text-green-700',
}

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-blue-100 text-blue-700',
  diagnosing: 'bg-purple-100 text-purple-700',
  awaiting_input: 'bg-yellow-100 text-yellow-700',
  resolved: 'bg-green-100 text-green-700',
  closed: 'bg-gray-100 text-gray-600',
}

interface Props {
  incident: Incident
  onRefresh: () => void
}

export default function IncidentCard({ incident, onRefresh }: Props) {
  const navigate = useNavigate()

  async function handleDiagnose(e: React.MouseEvent) {
    e.stopPropagation()
    try {
      await triggerDiagnosis(incident.id)
      onRefresh()
    } catch (err: any) {
      alert(err.message)
    }
  }

  const severityClass = SEVERITY_COLORS[incident.severity] ?? 'bg-gray-100 text-gray-600'
  const statusClass   = STATUS_COLORS[incident.status]    ?? 'bg-gray-100 text-gray-600'

  return (
    <div
      onClick={() => navigate(`/incidents/${incident.id}`)}
      className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md cursor-pointer transition"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${severityClass}`}>
              {incident.severity}
            </span>
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusClass}`}>
              {incident.status.replace('_', ' ')}
            </span>
          </div>
          <h3 className="text-sm font-semibold text-gray-800 truncate">{incident.title}</h3>
          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{incident.description}</p>
          <div className="flex gap-3 mt-2 text-xs text-gray-400">
            {incident.affected_device && <span>Device: {incident.affected_device}</span>}
            {incident.affected_protocol && <span>Protocol: {incident.affected_protocol.toUpperCase()}</span>}
          </div>
        </div>

        <div className="flex flex-col items-end gap-2 shrink-0">
          <span className="text-xs text-gray-400">
            {new Date(incident.created_at).toLocaleDateString()}
          </span>
          {incident.status === 'open' && (
            <button
              onClick={handleDiagnose}
              className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded-lg transition"
            >
              Diagnose
            </button>
          )}
          {incident.ai_report && (
            <span className="text-xs text-green-600 font-medium">✓ Report ready</span>
          )}
        </div>
      </div>
    </div>
  )
}
