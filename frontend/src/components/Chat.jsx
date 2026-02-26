import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, FileText, ChevronDown, ChevronRight, AlertTriangle, CheckCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { chatApi } from '../api';

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [selectedSource, setSelectedSource] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await chatApi.sendMessage(input, conversationId);
      
      setConversationId(response.conversation_id);
      
      const assistantMessage = {
        role: 'assistant',
        content: response.response,
        citations: response.citations,
        confidence: response.confidence,
        intent: response.intent,
        flags: response.flags,
        latency_ms: response.latency_ms,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
        error: true,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleNewConversation = () => {
    setMessages([]);
    setConversationId(null);
    setSelectedSource(null);
  };

  const ConfidenceBadge = ({ confidence }) => {
    const styles = {
      high: 'bg-green-100 text-green-700',
      medium: 'bg-yellow-100 text-yellow-700',
      low: 'bg-red-100 text-red-700',
    };
    
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[confidence] || styles.medium}`}>
        {confidence} confidence
      </span>
    );
  };

  const FlagBadge = ({ flags }) => {
    if (!flags) return null;
    
    const activeFlags = Object.entries(flags)
      .filter(([key, value]) => value === true && key !== 'confidence')
      .map(([key]) => key.replace(/_/g, ' '));
    
    if (activeFlags.length === 0) return null;
    
    return (
      <div className="flex items-center gap-1 text-xs text-amber-600">
        <AlertTriangle className="w-3 h-3" />
        {activeFlags.join(', ')}
      </div>
    );
  };

  return (
    <div className="h-screen flex">
      {/* Chat area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Research Assistant</h2>
            <p className="text-sm text-slate-500">Ask questions about filings and documents</p>
          </div>
          <button
            onClick={handleNewConversation}
            className="px-4 py-2 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
          >
            New Conversation
          </button>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 && (
            <div className="text-center py-12">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-primary-100 flex items-center justify-center">
                <FileText className="w-8 h-8 text-primary-600" />
              </div>
              <h3 className="text-lg font-medium text-slate-900 mb-2">
                Welcome to Wealth Advisor Copilot
              </h3>
              <p className="text-slate-500 max-w-md mx-auto mb-6">
                Ask questions about SEC filings, client documents, and market research.
                I'll provide answers with citations from your documents.
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {[
                  'What are the main risk factors in Apple\'s latest 10-K?',
                  'Summarize the revenue growth trends',
                  'Draft an email about portfolio performance',
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setInput(suggestion)}
                    className="px-4 py-2 text-sm text-slate-600 bg-slate-100 rounded-full hover:bg-slate-200 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-3xl rounded-2xl px-5 py-4 ${
                  message.role === 'user'
                    ? 'bg-primary-600 text-white'
                    : message.error
                    ? 'bg-red-50 text-red-900'
                    : 'bg-white border border-slate-200 text-slate-900'
                }`}
              >
                {message.role === 'assistant' && !message.error && (
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-xs font-medium capitalize">
                      {message.intent || 'qa'}
                    </span>
                    {message.confidence && <ConfidenceBadge confidence={message.confidence} />}
                    {message.latency_ms && (
                      <span className="text-xs text-slate-400">{message.latency_ms}ms</span>
                    )}
                    <FlagBadge flags={message.flags} />
                  </div>
                )}
                
                <div className={`markdown-content ${message.role === 'user' ? 'text-white' : ''}`}>
                  <ReactMarkdown>{message.content}</ReactMarkdown>
                </div>

                {message.citations && message.citations.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-200">
                    <p className="text-xs font-medium text-slate-500 mb-2">Sources:</p>
                    <div className="space-y-1">
                      {message.citations.map((citation, cidx) => (
                        <button
                          key={cidx}
                          onClick={() => setSelectedSource(citation)}
                          className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700 hover:underline"
                        >
                          <span className="flex-shrink-0 w-5 h-5 rounded bg-primary-100 text-primary-700 text-xs flex items-center justify-center">
                            {cidx + 1}
                          </span>
                          <span className="truncate">{citation.doc_title}</span>
                          {citation.section && (
                            <span className="text-slate-400 truncate">— {citation.section}</span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border border-slate-200 rounded-2xl px-5 py-4">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-5 h-5 animate-spin text-primary-600" />
                  <span className="text-slate-500">Researching...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="bg-white border-t border-slate-200 p-4">
          <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
            <div className="flex items-center gap-4 bg-slate-50 rounded-xl px-4 py-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about filings, risks, or request a summary..."
                className="flex-1 bg-transparent border-none outline-none text-slate-900 placeholder-slate-400"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="p-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            <p className="text-xs text-slate-400 text-center mt-2">
              For educational purposes only. Not investment advice.
            </p>
          </form>
        </div>
      </div>

      {/* Sources panel */}
      <aside className="w-96 bg-white border-l border-slate-200 flex flex-col">
        <div className="p-4 border-b border-slate-200">
          <h3 className="font-semibold text-slate-900">Source Details</h3>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4">
          {selectedSource ? (
            <div>
              <h4 className="font-medium text-slate-900 mb-2">{selectedSource.doc_title}</h4>
              {selectedSource.section && (
                <p className="text-sm text-slate-500 mb-2">Section: {selectedSource.section}</p>
              )}
              {selectedSource.page && (
                <p className="text-sm text-slate-500 mb-2">Page: {selectedSource.page}</p>
              )}
              {selectedSource.url && (
                <a
                  href={selectedSource.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-primary-600 hover:underline mb-4 block"
                >
                  View original source →
                </a>
              )}
              <div className="bg-slate-50 rounded-lg p-4 mt-4">
                <p className="text-sm text-slate-600 leading-relaxed">{selectedSource.quote}</p>
              </div>
            </div>
          ) : (
            <div className="text-center text-slate-400 py-8">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>Click on a citation to view source details</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
