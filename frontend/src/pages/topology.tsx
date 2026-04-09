import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Handle,
  MiniMap,
  Node,
  NodeProps,
  Position,
  useEdgesState,
  useNodesState,
} from 'reactflow'
import 'reactflow/dist/style.css'
import {
  listTopologies,
  simulateFailure,
  SimulateResponse,
  TopologyDevice,
  TopologyEdge,
  TopologyRecord,
} from '../services/api_client'

// ── Custom node ─────────────────────────────────────────────────────────────

function DeviceNode({ data }: NodeProps) {
  const vendorColor = data.vendor === 'cisco' ? '#1d6fa4' : '#d95f00'
  const ringClass = data.affected ? 'border-red-500 bg-red-50' : 'border-slate-300 bg-white'
  return (
    <div className={`rounded-lg border-2 px-3 py-2 shadow-md text-xs w-36 ${ringClass}`}>
      <Handle type="target" position={Position.Top} style={{ background: vendorColor }} />
      <div className="flex items-center gap-1 mb-1">
        <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: vendorColor }} />
        <span className="font-bold text-slate-800 truncate">{data.label}</span>
      </div>
      <div className="text-slate-500">{data.vendor} · {data.os}</div>
      <div className="text-slate-400 capitalize">{data.role}</div>
      {data.protocols.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-0.5">
          {data.protocols.map((p: string) => (
            <span key={p} className="px-1 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600">{p}</span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ background: vendorColor }} />
    </div>
  )
}

const nodeTypes = { device: DeviceNode }

// ── Fixed layout for the 5-node lab ─────────────────────────────────────────

const FIXED_POS: Record<string, { x: number; y: number }> = {
  r1: { x: 220, y: 30 },
  r2: { x: 60,  y: 200 },
  r3: { x: 380, y: 200 },
  r4: { x: 60,  y: 370 },
  r5: { x: 380, y: 370 },
}

function posFor(id: string, idx: number) {
  return FIXED_POS[id] ?? { x: 80 + (idx % 3) * 220, y: 50 + Math.floor(idx / 3) * 180 }
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TopologyPage() {
  const [topology, setTopology] = useState<TopologyRecord | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selected, setSelected] = useState<string | null>(null)
  const [simulation, setSimulation] = useState<SimulateResponse | null>(null)
  const [simLoading, setSimLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load topology list, pick the default
  useEffect(() => {
    listTopologies()
      .then((list) => {
        const t = list.find((x) => x.is_default) ?? list[0]
        if (!t) throw new Error('No topology found. Upload one first via /api/v1/topology/upload.')
        setTopology(t)
      })
      .catch((e) => {
        if (e.message.includes('expired') || e.message.includes('token') || e.message.includes('401')) {
          window.location.href = '/login'
        } else {
          setError(e.message)
        }
      })
  }, [])

  // Build React Flow nodes/edges whenever topology or simulation changes
  useEffect(() => {
    if (!topology?.graph_data) return
    const { nodes: devs, edges: links } = topology.graph_data

    const affectedDevices = new Set<string>()
    if (simulation) {
      affectedDevices.add(simulation.impact_analysis.failed_device)
      simulation.impact_analysis.isolated_devices.forEach((d) => affectedDevices.add(d.id))
    }

    const rfNodes: Node[] = devs.map((d, idx) => ({
      id: d.id,
      type: 'device',
      position: posFor(d.id, idx),
      data: {
        label: d.hostname,
        vendor: d.vendor,
        os: d.os,
        role: d.role,
        protocols: Object.keys(d.protocols),
        affected: affectedDevices.has(d.id),
      },
    }))

    const affectedDevice = simulation?.impact_analysis.failed_device
    const rfEdges: Edge[] = links.map((l, i) => {
      const isAffected =
        simulation != null &&
        (l.source === affectedDevice || l.target === affectedDevice)
      return {
        id: `e${i}`,
        source: l.source,
        target: l.target,
        label: `${l.local_iface}→${l.remote_iface}`,
        animated: !isAffected && l.status === 'up',
        style: {
          stroke: isAffected ? '#ef4444' : l.status === 'up' ? '#94a3b8' : '#fbbf24',
          strokeWidth: isAffected ? 3 : 2,
        },
        labelStyle: { fontSize: 9, fill: '#94a3b8' },
      }
    })

    setNodes(rfNodes)
    setEdges(rfEdges)
  }, [topology, simulation, setNodes, setEdges])

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelected((prev) => (prev === node.id ? null : node.id))
  }, [])

  const handleSimulate = useCallback(
    async (scenario: string) => {
      if (!topology) return
      setSimLoading(true)
      setSimulation(null)
      try {
        const result = await simulateFailure(topology.id, scenario)
        setSimulation(result)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setSimLoading(false)
      }
    },
    [topology],
  )

  const scenarios = useMemo(
    () => topology?.graph_data ? Object.keys(topology.graph_data.failure_scenarios ?? {}) : [],
    [topology],
  )

  const selectedDevice = useMemo(
    () => topology?.graph_data?.nodes.find((n) => n.id === selected),
    [topology, selected],
  )

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <h2 className="text-red-700 font-semibold mb-2">Failed to load topology</h2>
          <p className="text-red-600 text-sm">{error}</p>
          <button
            className="mt-4 text-sm text-blue-600 underline"
            onClick={() => { setError(null); listTopologies().then((l) => setTopology(l.find((x) => x.is_default) ?? l[0])).catch((e) => setError(e.message)) }}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!topology) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-pulse text-slate-500">Loading topology…</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center gap-4">
        <a href="/dashboard" className="text-slate-400 hover:text-slate-700 text-sm">← Dashboard</a>
        <h1 className="text-lg font-semibold text-slate-800">Network Topology</h1>
        <span className="text-sm text-slate-500">{topology.name}</span>
        <div className="ml-auto flex gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-[#1d6fa4] inline-block" /> Cisco</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-[#d95f00] inline-block" /> Juniper</span>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Graph canvas */}
        <div className="flex-1 h-[calc(100vh-57px)]">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
            fitViewOptions={{ padding: 0.25 }}
          >
            <Background gap={16} color="#e2e8f0" />
            <Controls />
            <MiniMap nodeColor={(n) => n.data.vendor === 'cisco' ? '#1d6fa4' : '#d95f00'} maskColor="rgba(241,245,249,0.8)" />
          </ReactFlow>
        </div>

        {/* Side panel */}
        <aside className="w-72 bg-white border-l border-slate-200 flex flex-col overflow-y-auto text-sm">
          {/* Failure scenarios */}
          <div className="p-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-700 mb-2 text-xs uppercase tracking-wide">Failure Scenarios</h2>
            <div className="flex flex-col gap-1">
              {scenarios.map((s) => (
                <button
                  key={s}
                  disabled={simLoading}
                  onClick={() => handleSimulate(s)}
                  className="text-left text-xs px-3 py-2 rounded border border-slate-200 hover:border-red-300 hover:bg-red-50 text-slate-600 transition disabled:opacity-50"
                >
                  {simLoading ? '⏳ ' : '⚡ '}{s.replace(/_/g, ' ')}
                </button>
              ))}
              {simulation && (
                <button onClick={() => setSimulation(null)} className="text-xs text-slate-400 underline mt-1 text-left">
                  Clear simulation
                </button>
              )}
            </div>
          </div>

          {/* Simulation result */}
          {simulation && (
            <div className="p-4 border-b border-slate-100">
              <h2 className="font-semibold text-red-600 mb-2 text-xs uppercase tracking-wide">Simulation Result</h2>
              <p className="text-xs text-slate-700 mb-2 font-medium">{simulation.failure_report.scenario}</p>
              <div className="text-xs text-slate-600 space-y-1">
                <div><span className="text-slate-400">Type:</span> {simulation.failure_report.type}</div>
                <div><span className="text-slate-400">Affected device:</span> {simulation.impact_analysis.failed_hostname}</div>
                <div><span className="text-slate-400">Isolated:</span> {simulation.impact_analysis.impact_count} device(s)</div>
              </div>
              {simulation.failure_report.changes.length > 0 && (
                <ul className="mt-2 text-xs text-slate-500 space-y-0.5 list-disc list-inside">
                  {simulation.failure_report.changes.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              )}
            </div>
          )}

          {/* Device detail */}
          {selectedDevice ? (
            <DeviceDetail device={selectedDevice} />
          ) : (
            <div className="p-4 text-xs text-slate-400 italic">Click a device to see details.</div>
          )}
        </aside>
      </div>
    </div>
  )
}

// ── Device detail panel ───────────────────────────────────────────────────────

function DeviceDetail({ device }: { device: TopologyDevice }) {
  const protocols = Object.keys(device.protocols)
  return (
    <div className="p-4">
      <h2 className="font-semibold text-slate-700 mb-3">{device.hostname}</h2>
      <dl className="text-xs space-y-1 text-slate-600">
        {[
          ['Vendor', device.vendor],
          ['OS', device.os],
          ['Model', device.model],
          ['Role', device.role],
          ['Loopback', device.loopback],
        ].map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <dt className="text-slate-400">{k}</dt>
            <dd className="font-medium capitalize">{v}</dd>
          </div>
        ))}
      </dl>
      {protocols.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-slate-500 mb-1">Protocols</div>
          <div className="flex flex-wrap gap-1">
            {protocols.map((p) => (
              <span key={p} className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-xs">{p.toUpperCase()}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
