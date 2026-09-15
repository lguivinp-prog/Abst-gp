import React, { useState, useEffect, useRef } from 'react';
import { Send, Sparkles, Bot, User, AlertCircle, Info } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import apiClient from '../../../api/client';

interface CaseAssistantProps {
  caseId: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: Record<string, any>;
}

export const CaseAssistant: React.FC<CaseAssistantProps> = ({ caseId }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<{ configured: boolean; provider: string } | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchStatus();
  }, [caseId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const fetchStatus = async () => {
    try {
      const response = await apiClient.get(`/api/v6/cases/${caseId}/assistant/status`);
      setStatus({
        configured: response.data.configured,
        provider: response.data.provider_name
      });
      setStatusError(null);
      if (response.data.configured && messages.length === 0) {
        setMessages([
          {
            role: 'assistant',
            content: '¡Hola! Soy tu asistente de IA para este caso. Puedes preguntarme sobre los requerimientos, los proveedores, las ofertas, o pedirme un resumen del expediente. Ten en cuenta que solo puedo asesorarte y no realizaré acciones automáticas como adjudicar o modificar el caso.'
          }
        ]);
      }
    } catch (err: any) {
      console.error('Error fetching AI status', err);
      setStatusError(err?.response?.data?.detail || 'Error de conexión');
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const newQuestion = inputValue.trim();
    setInputValue('');
    setMessages(prev => [...prev, { role: 'user', content: newQuestion }]);
    setIsLoading(true);

    try {
      const response = await apiClient.post(`/api/v6/cases/${caseId}/assistant/chat`, {
        question: newQuestion
      });
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.data.answer,
        sources: response.data.sources
      }]);
    } catch (err: any) {
      console.error('Error sending message to AI', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err?.response?.data?.detail || 'Ocurrió un error inesperado.'}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  if (statusError) {
    return (
      <div className="p-6 bg-red-50 text-red-700 rounded-lg flex items-center gap-3">
        <AlertCircle size={24} />
        <div>
          <h3 className="font-semibold">Error al cargar Asistente</h3>
          <p>{statusError}</p>
        </div>
      </div>
    );
  }

  if (status && !status.configured) {
    return (
      <div className="p-8 flex flex-col items-center justify-center text-center bg-gray-50 rounded-xl border border-gray-200 mt-4">
        <Sparkles size={48} className="text-gray-400 mb-4" />
        <h3 className="text-xl font-semibold text-gray-800 mb-2">Asistente de IA no configurado</h3>
        <p className="text-gray-600 max-w-md">
          El proveedor de IA no está configurado (API keys faltantes). Contacta al administrador para habilitar esta funcionalidad.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-250px)] bg-white rounded-xl border border-gray-200 shadow-sm mt-4">
      <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center bg-gray-50 rounded-t-xl">
        <div className="flex items-center gap-2">
          <Sparkles className="text-primary-600" size={20} />
          <h3 className="font-semibold text-gray-800">Asistente IA del Caso</h3>
        </div>
        {status?.provider && (
          <div className="flex items-center gap-1 text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
            <Info size={14} />
            Provider: {status.provider}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${msg.role === 'user' ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-700'}`}>
              {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className={`max-w-[75%] rounded-lg px-4 py-3 ${msg.role === 'user' ? 'bg-primary-600 text-white' : 'bg-gray-50 border border-gray-100 text-gray-800'}`}>
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              
              {msg.sources && Object.keys(msg.sources).length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <p className="text-xs text-gray-500 font-medium mb-1">Fuentes utilizadas:</p>
                  <ul className="text-xs text-gray-500 list-disc pl-4">
                    {Object.keys(msg.sources).map(key => (
                      <li key={key}>{key}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="flex gap-4">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-100 text-gray-700 flex items-center justify-center">
              <Bot size={18} />
            </div>
            <div className="bg-gray-50 border border-gray-100 rounded-lg px-4 py-4 flex items-center gap-2 text-gray-500">
              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-gray-200">
        <form onSubmit={handleSendMessage} className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Pregunta sobre este expediente..."
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
            disabled={isLoading}
          />
          <Button
            type="submit"
            disabled={!inputValue.trim() || isLoading}
            className="rounded-lg px-4"
          >
            <Send size={20} />
          </Button>
        </form>
      </div>
    </div>
  );
};
