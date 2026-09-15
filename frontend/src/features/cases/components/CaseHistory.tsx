import React, { useState, useEffect } from 'react';
import { casesService } from '../../../api/cases.service';
import { Clock, CheckCircle, Info, AlertTriangle, XCircle } from 'lucide-react';

interface CaseHistoryProps {
  caseId: string;
}

export const CaseHistory: React.FC<CaseHistoryProps> = ({ caseId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<any[]>([]);

  useEffect(() => {
    loadData();
  }, [caseId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await casesService.getHistory(caseId);
      setLogs(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || 'Error al cargar historial');
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    if (status === 'SUCCESS') return <CheckCircle size={16} className="text-green-600" />;
    if (status === 'WARNING') return <AlertTriangle size={16} className="text-yellow-600" />;
    if (status === 'ERROR') return <XCircle size={16} className="text-red-600" />;
    return <Info size={16} className="text-blue-600" />;
  };

  if (loading) return <div>Cargando historial...</div>;

  return (
    <div className="p-6">
      <div className="mb-6 border-b pb-4">
        <h2 className="text-2xl font-bold flex items-center gap-2"><Clock /> Historial del Expediente</h2>
        <p className="text-gray-500">Registro de auditoría y eventos clave.</p>
      </div>

      {error && <div className="text-red-600 mb-4">{error}</div>}

      <div className="relative border-l-2 border-gray-200 ml-4 pl-6 space-y-6">
        {logs.length === 0 ? (
          <p className="text-gray-500">No hay eventos registrados.</p>
        ) : (
          logs.map(log => (
            <div key={log.id} className="relative">
              <div className="absolute -left-9 top-1 bg-white p-1 rounded-full border border-gray-200">
                {getStatusIcon(log.status)}
              </div>
              <div className="bg-white p-4 border rounded shadow-sm">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="font-bold text-gray-800">{log.action}</h3>
                  <span className="text-xs text-gray-500">{new Date(log.created_at).toLocaleString()}</span>
                </div>
                <p className="text-sm text-gray-600 mb-2">{log.details}</p>
                <div className="text-xs text-gray-400 flex gap-4">
                  <span>Usuario ID: {log.user_id}</span>
                  <span>Entidad: {log.entity_type}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
