import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  AlertTriangle, 
  Clock, 
  MessageSquare, 
  TrendingUp,
  Filter,
  ChevronDown,
  ChevronUp,
  Eye,
  X
} from 'lucide-react';
import { adminApi } from '../api';
import { format } from 'date-fns';

export default function Admin() {
  const [selectedLog, setSelectedLog] = useState(null);
  const [filters, setFilters] = useState({
    workflow: '',
    confidence: '',
    has_flags: null,
  });

  const { data: stats } = useQuery({
    queryKey: ['audit-stats'],
    queryFn: () => adminApi.getStats(7),
  });

  const { data: logs, isLoading } = useQuery({
    queryKey: ['audit-logs', filters],
    queryFn: () => adminApi.getAuditLogs(1, 50, filters),
  });

  const { data: flaggedLogs } = useQuery({
    queryKey: ['flagged-logs'],
    queryFn: () => adminApi.getFlaggedResponses(1, 10),
  });

  const StatCard = ({ icon: Icon, label, value, subvalue, color }) => (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="text-2xl font-bold text-slate-900">{value}</p>
          <p className="text-sm text-slate-500">{label}</p>
        </div>
      </div>
      {subvalue && <p className="text-xs text-slate-400 mt-2">{subvalue}</p>}
    </div>
  );

  const confidenceColors = {
    high: 'bg-green-100 text-green-700',
    medium: 'bg-yellow-100 text-yellow-700',
    low: 'bg-red-100 text-red-700',
  };

  const workflowColors = {
    qa: 'bg-blue-100 text-blue-700',
    summary: 'bg-purple-100 text-purple-700',
    risk: 'bg-orange-100 text-orange-700',
    email: 'bg-green-100 text-green-700',
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <h2 className="text-lg font-semibold text-slate-900">Audit & Compliance</h2>
        <p className="text-sm text-slate-500">Monitor queries, responses, and compliance flags</p>
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-4 gap-4">
          <StatCard
            icon={MessageSquare}
            label="Total Queries"
            value={stats?.total_queries || 0}
            subvalue="Last 7 days"
            color="bg-primary-100 text-primary-600"
          />
          <StatCard
            icon={Clock}
            label="Avg Latency"
            value={`${Math.round(stats?.avg_latency_ms || 0)}ms`}
            subvalue="Response time"
            color="bg-slate-100 text-slate-600"
          />
          <StatCard
            icon={AlertTriangle}
            label="Flagged"
            value={
              (stats?.low_evidence_count || 0) +
              (stats?.possible_hallucination_count || 0)
            }
            subvalue="Needs review"
            color="bg-amber-100 text-amber-600"
          />
          <StatCard
            icon={TrendingUp}
            label="Refused"
            value={stats?.advice_refused_count || 0}
            subvalue="No evidence cases"
            color="bg-red-100 text-red-600"
          />
        </div>

        {/* Confidence Distribution */}
        {stats?.confidence_distribution && (
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="font-medium text-slate-900 mb-4">Confidence Distribution</h3>
            <div className="flex gap-4">
              {Object.entries(stats.confidence_distribution).map(([level, count]) => (
                <div key={level} className="flex items-center gap-2">
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${confidenceColors[level] || confidenceColors.medium}`}>
                    {level}: {count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Flagged Responses Alert */}
        {flaggedLogs?.logs?.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              <h3 className="font-medium text-amber-900">
                {flaggedLogs.total} Responses Need Review
              </h3>
            </div>
            <div className="space-y-2">
              {flaggedLogs.logs.slice(0, 3).map((log) => (
                <button
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className="w-full text-left p-3 bg-white rounded-lg hover:bg-amber-100 transition-colors"
                >
                  <p className="text-sm text-slate-900 truncate">{log.user_query}</p>
                  <div className="flex items-center gap-2 mt-1">
                    {Object.entries(log.flags)
                      .filter(([k, v]) => v === true && k !== 'confidence')
                      .map(([flag]) => (
                        <span key={flag} className="text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded">
                          {flag.replace(/_/g, ' ')}
                        </span>
                      ))}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-4">
            <Filter className="w-5 h-5 text-slate-400" />
            <select
              value={filters.workflow}
              onChange={(e) => setFilters({ ...filters, workflow: e.target.value })}
              className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm"
            >
              <option value="">All Workflows</option>
              <option value="qa">Q&A</option>
              <option value="summary">Summary</option>
              <option value="risk">Risk Analysis</option>
              <option value="email">Email Draft</option>
            </select>
            <select
              value={filters.confidence}
              onChange={(e) => setFilters({ ...filters, confidence: e.target.value })}
              className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm"
            >
              <option value="">All Confidence</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={filters.has_flags === true}
                onChange={(e) => setFilters({ ...filters, has_flags: e.target.checked ? true : null })}
                className="rounded border-slate-300"
              />
              Flagged only
            </label>
          </div>
        </div>

        {/* Audit Logs Table */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600">Query</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600">Workflow</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600">Confidence</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600">Chunks</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600">Latency</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600">Flags</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600">Time</th>
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-600"></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                      Loading audit logs...
                    </td>
                  </tr>
                ) : logs?.logs?.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                      No audit logs found
                    </td>
                  </tr>
                ) : (
                  logs?.logs?.map((log) => (
                    <tr key={log.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <p className="text-sm text-slate-900 truncate max-w-xs">{log.user_query}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${workflowColors[log.workflow] || workflowColors.qa}`}>
                          {log.workflow}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${confidenceColors[log.confidence_level] || confidenceColors.medium}`}>
                          {log.confidence_level}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-600">
                        {log.retrieved_chunk_count}
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-600">
                        {log.latency_ms}ms
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1">
                          {Object.entries(log.flags)
                            .filter(([k, v]) => v === true && k !== 'confidence')
                            .slice(0, 2)
                            .map(([flag]) => (
                              <span key={flag} className="w-2 h-2 rounded-full bg-amber-500" title={flag} />
                            ))}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-500">
                        {format(new Date(log.created_at), 'MMM d, HH:mm')}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => setSelectedLog(log)}
                          className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900">Audit Log Details</h3>
              <button onClick={() => setSelectedLog(null)} className="p-2 hover:bg-slate-100 rounded-lg">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-500 mb-1">User Query</label>
                <p className="text-slate-900 bg-slate-50 rounded-lg p-3">{selectedLog.user_query}</p>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-500 mb-1">Workflow</label>
                  <span className={`px-3 py-1 rounded text-sm font-medium ${workflowColors[selectedLog.workflow]}`}>
                    {selectedLog.workflow}
                  </span>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-500 mb-1">Confidence</label>
                  <span className={`px-3 py-1 rounded text-sm font-medium ${confidenceColors[selectedLog.confidence_level]}`}>
                    {selectedLog.confidence_level}
                  </span>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-500 mb-1">Model</label>
                  <p className="text-slate-900">{selectedLog.model_name}</p>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-500 mb-1">Response</label>
                <div className="text-slate-900 bg-slate-50 rounded-lg p-3 whitespace-pre-wrap max-h-64 overflow-y-auto">
                  {selectedLog.response_text}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-500 mb-1">Flags</label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(selectedLog.flags).map(([flag, value]) => (
                    <span
                      key={flag}
                      className={`px-2 py-1 rounded text-xs ${
                        value === true
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {flag.replace(/_/g, ' ')}: {String(value)}
                    </span>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-500 mb-1">Retrieved Chunks</label>
                  <p className="text-slate-900">{selectedLog.retrieved_chunk_count}</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-500 mb-1">Latency</label>
                  <p className="text-slate-900">{selectedLog.latency_ms}ms</p>
                </div>
              </div>
              {selectedLog.citations && Object.keys(selectedLog.citations).length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-slate-500 mb-1">Citations</label>
                  <pre className="text-xs text-slate-700 bg-slate-50 rounded-lg p-3 overflow-x-auto">
                    {JSON.stringify(selectedLog.citations, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
