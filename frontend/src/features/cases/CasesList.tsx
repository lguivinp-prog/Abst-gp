import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PlusCircle, Search, Clock, FileText, CheckCircle, AlertCircle } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import type { Case, CaseCreate } from '../../types';
import { CreateCaseModal } from './components/CreateCaseModal';
import { casesService } from '../../api/cases.service';
import { AppError } from '../../api/apiError';
import { RoleGuard } from '../../components/Auth/RoleGuard';
import './CasesList.css';

const CasesList: React.FC = () => {
  const [cases, setCases] = useState<Case[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    fetchCases();
  }, []);

  const fetchCases = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await casesService.getCases();
      setCases(data);
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error inesperado al cargar expedientes.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreateCase = async (payload: CaseCreate) => {
    await casesService.createCase(payload);
    await fetchCases();
  };

  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'CREATED': return { icon: <Clock size={16} />, color: 'secondary', text: 'Borrador' };
      case 'PROCESSING_REQUIREMENT': return { icon: <FileText size={16} />, color: 'warning', text: 'Procesando req.' };
      case 'REVIEW_SECTIONS': return { icon: <AlertCircle size={16} />, color: 'warning', text: 'Revisión req.' };
      case 'WAITING_QUOTATION': return { icon: <Clock size={16} />, color: 'primary', text: 'Espera Cotización' };
      case 'COMPARING': return { icon: <FileText size={16} />, color: 'primary', text: 'Comparando' };
      case 'READY_GENERATE': return { icon: <CheckCircle size={16} />, color: 'primary', text: 'Listo generar' };
      case 'COMPLETED': return { icon: <CheckCircle size={16} />, color: 'success', text: 'Completado' };
      case 'ERROR': return { icon: <AlertCircle size={16} />, color: 'danger', text: 'Error' };
      default: return { icon: <Clock size={16} />, color: 'secondary', text: status };
    }
  };

  const filteredCases = cases.filter(c => {
    const matchesSearch = c.title.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'ALL' || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="cases-list-container p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1">Expedientes de Contratación</h1>
          <p className="text-gray-500 text-sm">Gestione los requerimientos y cotizaciones</p>
        </div>
        <RoleGuard roles={['ADMIN', 'OPERATOR']}>
          <Button leftIcon={<PlusCircle size={18} />} onClick={() => setIsModalOpen(true)}>
            Nuevo Expediente
          </Button>
        </RoleGuard>
      </div>

      {error && (
        <div style={{ backgroundColor: '#fee2e2', color: '#b91c1c', padding: '0.75rem', borderRadius: '4px', marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      <div className="filters-section bg-white p-4 rounded-lg shadow-sm border border-gray-100 mb-6 flex gap-4">
        <div className="search-box flex-1 flex items-center bg-gray-50 border border-gray-200 rounded-md px-3 py-2">
          <Search size={18} className="text-gray-400 mr-2" />
          <input 
            type="text" 
            placeholder="Buscar por título..." 
            className="bg-transparent border-none outline-none w-full text-sm"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        
        <select 
          className="border border-gray-200 rounded-md px-3 py-2 text-sm bg-white outline-none"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="ALL">Todos los estados</option>
          <option value="CREATED">Borrador</option>
          <option value="PROCESSING_REQUIREMENT">Procesando req.</option>
          <option value="REVIEW_SECTIONS">Revisión req.</option>
          <option value="WAITING_QUOTATION">Espera Cotización</option>
          <option value="COMPLETED">Completado</option>
          <option value="ERROR">Error</option>
        </select>
      </div>

      {loading ? (
        <div className="py-12 flex justify-center">
          <div className="spinner"></div>
        </div>
      ) : filteredCases.length === 0 ? (
        <div className="empty-state text-center py-12 bg-gray-50 rounded-lg border border-dashed border-gray-300">
          <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center mx-auto mb-4 shadow-sm">
            <FileText size={24} className="text-gray-400" />
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-1">No hay expedientes</h3>
          <p className="text-gray-500 text-sm mb-4">No se encontraron expedientes con los filtros actuales.</p>
          <Button variant="outline" onClick={() => setIsModalOpen(true)}>Crear el primero</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredCases.map(c => {
            const statusConfig = getStatusConfig(c.status);
            return (
              <Link to={`/cases/${c.id}`} key={c.id} className="block no-underline">
                <Card className="h-full hover:shadow-md transition-shadow cursor-pointer">
                  <CardHeader className="pb-2">
                    <div className="flex justify-between items-start">
                      <Badge variant={statusConfig.color as any} className="mb-2 flex items-center gap-1">
                        {statusConfig.icon}
                        <span>{statusConfig.text}</span>
                      </Badge>
                      <span className="text-xs text-gray-400">
                        {new Date(c.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <CardTitle className="text-base line-clamp-2"><span title={c.title}>{c.title}</span></CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-sm text-gray-600 mb-3 flex flex-col gap-1">
                      <span className="flex items-center gap-1">
                        <Badge variant="secondary" className="text-xs">
                          {c.contract_type === 'bienes' ? 'BIENES' : 
                           c.contract_type === 'servicios' ? 'SERVICIOS' : 
                           c.contract_type === 'obras' ? 'OBRA' : 
                           c.contract_type === 'consultoria_obras' ? 'CONSULTORÍA DE OBRA' : 
                           c.contract_type.toUpperCase()}
                        </Badge>
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}

      <CreateCaseModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSubmit={handleCreateCase} 
      />
    </div>
  );
};

export default CasesList;
