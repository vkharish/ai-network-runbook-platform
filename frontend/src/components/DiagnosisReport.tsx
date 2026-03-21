import { useState } from 'react'
import { AIReport } from '../services/api_client'

const URGENCY_COLORS: Record<string, string> = {
  immediate: 'bg-red-100 text-red-700',
  high:      'bg-orange-100 text-orange-700',
  medium:    'bg-yellow-100 text-yellow-700',
  low:       'bg-green-100 text-green-700',
}

export default function DiagnosisReport({ report }: { report: AIReport }) {
  const [showOrchestration, setShowOrchestration] = useState(false)
  const confidencePct = Math.round(report.confidence * 100)
  const urgencyClass  = URGENCY_COLORS[report.urgency] ?? 'bg-gray-100 text-gray-600'

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="bg-blue-50 border border-blue-100 rounded-lg p-4">
        <p className="text-sm font-semibold text-blue-800 mb-1">Executive Summary</p>
        <p className="text-sm text-blue-700">{report.summary}</p>
      </div>

      {/* Root cause + confidence */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
        <div>
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Root Cause</p>
          <p className="text-sm text-gray-800">{report.root_cause}</p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex-1">
            <p className="text-xs text-gray-500 mb-1">Confidence</p>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${confidencePct >= 75 ? 'bg-green-500' : confidencePct >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`}
                style={{ width: `${confidencePct}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 mt-0.5">{confidencePct}%</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Urgency</p>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${urgencyClass}`}>
              {report.urgency}
            </span>
          </div>
        </div>

        {report.hypothesis && (
          <div>
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Hypothesis</p>
            <p className="text-sm text-gray-600">{report.hypothesis}</p>
          </div>
        )}
      </div>

      {/* Troubleshooting steps */}
      {report.steps.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">
            Troubleshooting Steps
          </p>
          <ol className="space-y-2">
            {report.steps.map((step, i) => (
              <li key={i} className="text-sm text-gray-700 flex gap-2">
                <span className="text-blue-600 font-semibold shrink-0">{i + 1}.</span>
                <span>{step.replace(/^\d+\.\s*/, '')}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* CLI Commands */}
      {report.commands.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-2">CLI Commands</p>
          <div className="space-y-1">
            {report.commands.map((cmd, i) => (
              <code key={i} className="block text-sm text-green-400 font-mono">
                $ {cmd}
              </code>
            ))}
          </div>
        </div>
      )}

      {/* Affected components */}
      {report.affected_components.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-2">
            Affected Components
          </p>
          <div className="flex flex-wrap gap-2">
            {report.affected_components.map((comp, i) => (
              <span key={i} className="text-xs bg-orange-50 text-orange-700 border border-orange-200 px-2 py-1 rounded">
                {comp}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Citations */}
      {report.citations.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-2">Sources</p>
          <div className="space-y-1">
            {report.citations.map((c, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-600">
                <span className="text-blue-500">📄</span>
                <span className="font-mono">{c.source}</span>
                <span className="text-gray-400">chunk {c.chunk_index}</span>
                <span className="text-gray-400">score {c.score.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Escalation */}
      {report.escalation && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <p className="text-xs text-amber-700 font-semibold mb-1">Escalation</p>
          <p className="text-sm text-amber-800">{report.escalation}</p>
        </div>
      )}

      {/* Orchestration debug panel */}
      {report.orchestration && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <button
            onClick={() => setShowOrchestration(!showOrchestration)}
            className="w-full text-left px-4 py-2 bg-gray-50 hover:bg-gray-100 text-xs text-gray-500 font-medium flex justify-between items-center"
          >
            <span>Agent Orchestration ({report.orchestration.agents_invoked?.join(' → ')})</span>
            <span>{showOrchestration ? '▲' : '▼'}</span>
          </button>
          {showOrchestration && (
            <div className="p-4 space-y-2">
              <div className="flex gap-4 text-xs text-gray-600">
                <span>Iterations: <strong>{report.orchestration.total_iterations}</strong></span>
                <span>Provider: <strong>{report.llm_provider}</strong></span>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">Decision log:</p>
                <ol className="space-y-0.5">
                  {report.orchestration.decisions?.map((d, i) => (
                    <li key={i} className="text-xs text-gray-500 font-mono">{d}</li>
                  ))}
                </ol>
              </div>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-gray-400 text-right">
        Generated: {new Date(report.generated_at).toLocaleString()}
      </p>
    </div>
  )
}
