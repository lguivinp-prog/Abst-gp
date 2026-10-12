import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Building2, Mail, User, ShieldCheck } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { supplierService } from '../../../api/v6/supplier.service';
import type { CaseSupplierResponse, SupplierCreate } from '../../../api/v6/supplier.types';
import { AppError } from '../../../api/apiError';
import './CaseSuppliers.css';

interface CaseSuppliersProps {
  caseId: string;
  caseStatus?: string;
}

export const CaseSuppliers: React.FC<CaseSuppliersProps> = ({ caseId, caseStatus }) => {
  const [suppliers, setSuppliers] = useState<CaseSupplierResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const validStatuses = ["WAITING_QUOTATION", "COMPARING", "READY_GENERATE", "UNDER_REVIEW", "APPROVED", "COMPLETED"];
  const isTerminal = caseStatus === "APPROVED" || caseStatus === "COMPLETED";
  const isReviewPending = !caseStatus || !validStatuses.includes(caseStatus);
  const isMutationBlocked = isReviewPending || isTerminal;

  const [showAddForm, setShowAddForm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const [formData, setFormData] = useState<SupplierCreate>({
    ruc: '',
    business_name: '',
    legal_representative: '',
    dni: '',
    contact_email: ''
  });

  const loadSuppliers = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await supplierService.getCaseSuppliers(caseId);
      setSuppliers(data);
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error inesperado al cargar los proveedores.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSuppliers();
  }, [caseId]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleAddSupplier = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isMutationBlocked) return;
    if (!formData.ruc || !formData.business_name) {
      setError('RUC y Razón Social son obligatorios.');
      return;
    }
    
    setIsSubmitting(true);
    setError(null);
    
    try {
      await supplierService.linkCaseSupplier(caseId, formData);
      setFormData({
        ruc: '',
        business_name: '',
        legal_representative: '',
        dni: '',
        contact_email: ''
      });
      setShowAddForm(false);
      await loadSuppliers();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error al vincular el proveedor.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUnlink = async (supplierId: number) => {
    if (isMutationBlocked) return;
    if (!window.confirm('¿Está seguro de desvincular este proveedor del expediente?')) {
      return;
    }
    
    setError(null);
    try {
      await supplierService.unlinkCaseSupplier(caseId, supplierId);
      await loadSuppliers();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error al desvincular el proveedor.');
      }
    }
  };

  if (loading && suppliers.length === 0) {
    return (
      <div className="case-suppliers-loading">
        <div className="spinner"></div>
        <p>Cargando proveedores...</p>
      </div>
    );
  }

  return (
    <div className="case-suppliers-container">
      <div className="case-suppliers-header">
        <div>
          <h2>Proveedores Participantes</h2>
          <p>Gestione los proveedores vinculados a este expediente y sus ofertas.</p>
        </div>
        {!showAddForm && (
          <Button 
            onClick={() => setShowAddForm(true)} 
            leftIcon={<Plus size={16} />}
            disabled={isMutationBlocked}
            title={isTerminal ? "El expediente está cerrado" : (isReviewPending ? "Debe confirmar el requerimiento antes de agregar proveedores" : "")}
          >
            Vincular Proveedor
          </Button>
        )}
      </div>

      {isReviewPending && (
        <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-6 rounded-md">
          <div className="flex">
            <div className="flex-shrink-0">
              <ShieldCheck className="h-5 w-5 text-yellow-400" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-yellow-700">
                <strong>Requerimiento pendiente de confirmación:</strong> Debe confirmar el requerimiento en la pestaña "Requerimiento" antes de poder vincular proveedores o ingresar ofertas.
              </p>
            </div>
          </div>
        </div>
      )}

      {error && <div className="case-suppliers-error">{error}</div>}

      {showAddForm && (
        <div className="case-suppliers-form-card">
          <h3>Vincular nuevo proveedor</h3>
          <form onSubmit={handleAddSupplier} className="case-suppliers-form">
            <div className="form-group">
              <label>RUC *</label>
              <input 
                type="text" 
                name="ruc" 
                value={formData.ruc} 
                onChange={handleInputChange} 
                maxLength={11}
                placeholder="Ej. 20123456789" 
                required 
              />
            </div>
            <div className="form-group">
              <label>Razón Social *</label>
              <input 
                type="text" 
                name="business_name" 
                value={formData.business_name} 
                onChange={handleInputChange} 
                placeholder="Nombre de la empresa" 
                required 
              />
            </div>
            <div className="form-group">
              <label>Representante Legal</label>
              <input 
                type="text" 
                name="legal_representative" 
                value={formData.legal_representative || ''} 
                onChange={handleInputChange} 
                placeholder="Nombre completo" 
              />
            </div>
            <div className="form-group">
              <label>DNI Representante</label>
              <input 
                type="text" 
                name="dni" 
                value={formData.dni || ''} 
                onChange={handleInputChange} 
                maxLength={8}
                placeholder="DNI" 
              />
            </div>
            <div className="form-group">
              <label>Correo Electrónico</label>
              <input 
                type="email" 
                name="contact_email" 
                value={formData.contact_email || ''} 
                onChange={handleInputChange} 
                placeholder="correo@empresa.com" 
              />
            </div>
            <div className="form-actions">
              <Button type="button" variant="ghost" onClick={() => setShowAddForm(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Guardando...' : 'Vincular'}
              </Button>
            </div>
          </form>
        </div>
      )}

      {!showAddForm && suppliers.length === 0 && (
        <div className="case-suppliers-empty">
          <Building2 size={48} className="empty-icon" />
          <h3>No hay proveedores vinculados</h3>
          <p>No se han registrado proveedores para este expediente.</p>
          <Button onClick={() => setShowAddForm(true)} variant="outline" disabled={isMutationBlocked} title={isTerminal ? "El expediente está cerrado" : ""}>
            Vincular el primero
          </Button>
        </div>
      )}

      {suppliers.length > 0 && (
        <div className="case-suppliers-list">
          {suppliers.map(sup => (
            <div key={sup.id} className="case-supplier-card">
              <div className="case-supplier-info">
                <div className="case-supplier-name-row">
                  <h4>{sup.business_name}</h4>
                  <Badge variant={sup.status === 'APPROVED' ? 'success' : 'secondary'}>
                    {sup.status || 'PENDING'}
                  </Badge>
                </div>
                <div className="case-supplier-details">
                  <div className="detail-item">
                    <ShieldCheck size={14} />
                    <span>RUC: {sup.ruc}</span>
                  </div>
                  {sup.legal_representative && (
                    <div className="detail-item">
                      <User size={14} />
                      <span>Rep: {sup.legal_representative} {sup.dni ? `(${sup.dni})` : ''}</span>
                    </div>
                  )}
                  {sup.contact_email && (
                    <div className="detail-item">
                      <Mail size={14} />
                      <span>{sup.contact_email}</span>
                    </div>
                  )}
                </div>
              </div>
              <div className="case-supplier-actions">
                <Button 
                  variant="ghost" 
                  className="btn-delete"
                  onClick={() => handleUnlink(sup.id)}
                  title={isTerminal ? "El expediente está cerrado" : "Desvincular"}
                  disabled={isMutationBlocked}
                >
                  <Trash2 size={16} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

