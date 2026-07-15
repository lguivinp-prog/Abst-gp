import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, FileText, Search, Clock } from 'lucide-react';
import apiClient from '../../api/client';
import type { Case } from '../../types';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import './CasesList.css';

const CasesList: React.FC = () => {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newCase, setNewCase] = useState({ title: '', contract_type: 'bienes', siga_number: '', office_unit: '' });
  const [isCreating, setIsCreating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchCases();
  }, []);

  const fetchCases = async () => {
    try {
      const response = await apiClient.get('/cases/');
      setCases(response.data);
    } catch (error) {
      console.error('Error fetching cases:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'CREATED': return 'Borrador';
      case 'PROCESSING_REQUIREMENT': return 'Procesando requerimiento';
      case 'REVIEW_SECTIONS': return 'Revisar secciones';
      case 'WAITING_QUOTATION': return 'Esperando cotización';
      case 'COMPARING': return 'Comparando';
      case 'READY_GENERATE': return 'Listo para generar';
      case 'COMPLETED': return 'Completado';
      case 'ERROR': return 'Error';
      default: return status;
    }
  };

  const getStatusBadge = (status: string) => {
    const label = getStatusLabel(status);
    switch (status) {
      case 'CREATED': return <Badge variant="secondary">{label}</Badge>;
      case 'PROCESSING_REQUIREMENT': return <Badge variant="warning">{label}</Badge>;
      case 'REVIEW_SECTIONS': return <Badge variant="warning">{label}</Badge>;
      case 'WAITING_QUOTATION': return <Badge variant="primary">{label}</Badge>;
      case 'COMPARING': return <Badge variant="primary">{label}</Badge>;
      case 'READY_GENERATE': return <Badge variant="primary">{label}</Badge>;
      case 'COMPLETED': return <Badge variant="success">{label}</Badge>;
      case 'ERROR': return <Badge variant="danger">{label}</Badge>;
      default: return <Badge variant="secondary">{label}</Badge>;
    }
  };

  const handleCreateCase = async () => {
    if (!newCase.title.trim()) {
        setErrorMsg('El título es requerido');
        return;
    }
    setIsCreating(true);
    setErrorMsg(null);
    try {
      await apiClient.post('/cases/', newCase);
      setIsModalOpen(false);
      setNewCase({ title: '', contract_type: 'bienes', siga_number: '', office_unit: '' });
      fetchCases();
    } catch (err: any) {
      console.error('Error creating case:', err);
      setErrorMsg(err.response?.data?.detail || 'Error al crear expediente');
    } finally {
      setIsCreating(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('es-PE', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  };

  return (
    <div className="cases-list-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Expedientes de Contratación</h1>
          <p className="page-subtitle">Gestione los requerimientos y cotizaciones</p>
        </div>
        <Button leftIcon={<Plus size={18} />} onClick={() => setIsModalOpen(true)}>
          Nuevo Expediente
        </Button>
      </div>

      <div className="filters-bar">
        <div className="search-input-wrapper">
          <Search size={18} className="search-icon" />
          <input type="text" className="search-input" placeholder="Buscar expedientes..." />
        </div>
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Cargando expedientes...</p>
        </div>
      ) : cases.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-icon-wrapper">
            <FileText size={48} className="empty-icon" />
          </div>
          <h3>No hay expedientes</h3>
          <p>Comience creando un nuevo expediente de contratación.</p>
          <Button leftIcon={<Plus size={18} />} className="mt-4" onClick={() => setIsModalOpen(true)}>
            Crear Expediente
          </Button>
        </div>
      ) : (
        <div className="cases-grid">
          {cases.map((c) => (
            <Link to={`/cases/${c.id}`} key={c.id} className="case-card-link">
              <Card className="case-card hover-effect">
                <CardHeader>
                  <div className="case-card-header-top">
                    {getStatusBadge(c.status)}
                    <span className="case-type">{c.contract_type.toUpperCase()}</span>
                  </div>
                  <CardTitle className="case-title">{c.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="case-meta">
                    <div className="meta-item">
                      <Clock size={16} />
                      <span>{formatDate(c.created_at)}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {isModalOpen && (
        <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50">
          <Card className="w-[500px] shadow-2xl">
            <CardHeader>
              <CardTitle>Nuevo Expediente</CardTitle>
            </CardHeader>
            <CardContent>
              {errorMsg && <div className="text-red-600 mb-4 text-sm">{errorMsg}</div>}
              <div className="flex flex-col gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Título *</label>
                  <input type="text" className="w-full p-2 border rounded" value={newCase.title} onChange={e => setNewCase({...newCase, title: e.target.value})} placeholder="Ej: Adquisición de Laptops" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Tipo de Contratación *</label>
                  <select className="w-full p-2 border rounded" value={newCase.contract_type} onChange={e => setNewCase({...newCase, contract_type: e.target.value})}>
                    <option value="bienes">Bienes</option>
                    <option value="servicios">Servicios</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">N° SIGA (Opcional)</label>
                  <input type="text" className="w-full p-2 border rounded" value={newCase.siga_number} onChange={e => setNewCase({...newCase, siga_number: e.target.value})} placeholder="0001-2026" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Unidad Orgánica (Opcional)</label>
                  <input type="text" className="w-full p-2 border rounded" value={newCase.office_unit} onChange={e => setNewCase({...newCase, office_unit: e.target.value})} placeholder="Oficina de TI" />
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-6">
                <Button variant="outline" onClick={() => setIsModalOpen(false)}>Cancelar</Button>
                <Button onClick={handleCreateCase} disabled={isCreating}>{isCreating ? 'Creando...' : 'Crear'}</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default CasesList;
