import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { queryRunbooks, uploadRunbook, RAGQueryResponse } from '../services/api_client'

interface Message {
  role: 'user' | 'assistant'
  text: string
  response?: RAGQueryResponse
}

export default function RunbookChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const [tags, setTags]         = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return

    const query = input.trim()
    setInput('')
    setMessages(m => [...m, { role: 'user', text: query }])
    setLoading(true)

    try {
      const resp = await queryRunbooks(query, 5)
      setMessages(m => [...m, { role: 'assistant', text: resp.answer, response: resp }])
    } catch (err: any) {
      setMessages(m => [...m, { role: 'assistant', text: `Error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const title = prompt('Runbook title:', file.name.replace(/\.[^.]+$/, '')) ?? file.name
    setUploading(true)
    try {
      const tagList = tags.split(',').map(t => t.trim()).filter(Boolean)
      await uploadRunbook(file, title, tagList)
      alert(`"${title}" uploaded and queued for indexing.`)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <nav className="bg-gray-900 text-white px-6 py-3 flex items-center gap-4">
        <button onClick={() => navigate('/dashboard')} className="text-xs text-gray-400 hover:text-white">
          ← Dashboard
        </button>
        <span className="text-sm font-semibold">Runbook Knowledge Base</span>
        <div className="ml-auto flex items-center gap-3">
          <input
            placeholder="tags (cisco,bgp)"
            value={tags}
            onChange={e => setTags(e.target.value)}
            className="text-xs bg-gray-800 text-gray-200 border border-gray-700 rounded px-2 py-1 w-36"
          />
          <input ref={fileRef} type="file" accept=".pdf,.md,.txt" onChange={handleUpload} className="hidden" />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-3 py-1.5 rounded transition"
          >
            {uploading ? 'Uploading…' : '↑ Upload Runbook'}
          </button>
        </div>
      </nav>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto max-w-3xl mx-auto w-full px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 py-16 text-sm">
            <p className="text-2xl mb-2">📚</p>
            <p>Ask anything about your network runbooks.</p>
            <p className="text-xs mt-1">e.g. "BGP session stuck in Active state"</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
              msg.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'bg-white border border-gray-200 text-gray-800'
            }`}>
              <p className="whitespace-pre-wrap">{msg.text}</p>

              {/* Citations */}
              {msg.response && msg.response.results.length > 0 && (
                <details className="mt-3">
                  <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">
                    Sources ({msg.response.results.length})
                  </summary>
                  <div className="mt-2 space-y-1">
                    {msg.response.results.map((r, j) => (
                      <div key={j} className="text-xs text-gray-500 flex gap-2">
                        <span>📄 {r.source}</span>
                        <span className="text-gray-400">score {r.score.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-400">
              Searching runbooks…
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 bg-white px-4 py-3">
        <form onSubmit={handleSend} className="max-w-3xl mx-auto flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask about a network issue…"
            disabled={loading}
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit" disabled={loading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-5 py-2 rounded-lg disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
