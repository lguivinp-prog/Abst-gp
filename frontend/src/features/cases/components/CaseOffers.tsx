import React, { useState, useEffect } from 'react';
import { DollarSign, Trash2, Edit2, Check, X, FileText, AlertCircle, Building2 } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { offerService } from '../../../api/v6/offer.service';
import type { SupplierOfferResponse, SupplierOfferUpdate } from '../../../api/v6/offer.types';
import { AppError } from '../../../api/apiError';
import './CaseOffers.css';

interface CaseOffersProps {
  caseId: string;
}

export const CaseOffers: React.FC<CaseOffersProps> = ({ caseId }) => {
  const [offers, setOffers] = useState<SupplierOfferResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingOfferId, setEditingOfferId] = useState<number | null>(null);
  const [editData, setEditData] = useState<SupplierOfferUpdate>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadOffers = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await offerService.getOffers(caseId);
      setOffers(data);
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error inesperado al cargar las ofertas.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOffers();
  }, [caseId]);

  const handleEditClick = (offer: SupplierOfferResponse) => {
    setEditingOfferId(offer.id);
    setEditData({
      price: offer.price,
      source_document: offer.source_document,
      status: offer.status
    });
  };

  const handleCancelEdit = () => {
    setEditingOfferId(null);
    setEditData({});
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setEditData(prev => ({
      ...prev,
      [name]: name === 'price' ? (value ? parseFloat(value) : undefined) : value
    }));
  };

  const handleSaveOffer = async (offerId: number) => {
    setIsSubmitting(true);
    setError(null);

    try {
      await offerService.updateOffer(caseId, offerId, editData);
      setEditingOfferId(null);
      await loadOffers();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error al actualizar la oferta.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteOffer = async (offerId: number) => {
    if (!window.confirm('¿Está seguro de eliminar esta oferta?')) {
      return;
    }

    setError(null);
    try {
      await offerService.deleteOffer(caseId, offerId);
      await loadOffers();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error al eliminar la oferta.');
      }
    }
  };

  if (loading && offers.length === 0) {
    return (
      <div className="case-offers-loading">
        <div className="spinner"></div>
        <p>Cargando ofertas...</p>
      </div>
    );
  }

  return (
    <div className="case-offers-container">
      <div className="case-offers-header">
        <div>
          <h2>Ofertas de Proveedores</h2>
          <p>Gestione las cotizaciones y ofertas vinculadas a este expediente.</p>
        </div>
      </div>

      {error && <div className="case-offers-error"><AlertCircle size={16} /> {error}</div>}

      {offers.length === 0 && (
        <div className="case-offers-empty">
          <FileText size={48} className="empty-icon" />
          <h3>No hay ofertas registradas</h3>
          <p>Primero debe vincular un proveedor en la pestaña "Proveedores".</p>
        </div>
      )}

      {offers.length > 0 && (
        <div className="case-offers-list">
          {offers.map(offer => {
            const isEditing = editingOfferId === offer.id;
            const isCompleted = offer.price !== null && offer.price !== undefined;

            return (
              <div key={offer.id} className={`case-offer-card ${isEditing ? 'editing' : ''}`}>
                <div className="case-offer-header">
                  <div className="case-offer-supplier">
                    <Building2 size={18} />
                    <h4>{offer.supplier?.business_name || `Proveedor #${offer.supplier_id}`}</h4>
                    {offer.supplier?.ruc && <span className="supplier-ruc">RUC: {offer.supplier.ruc}</span>}
                  </div>
                  <div className="case-offer-status">
                    <Badge variant={isCompleted ? 'primary' : 'secondary'}>
                      {isCompleted ? 'Oferta completada' : 'Proveedor registrado'}
                    </Badge>
                  </div>
                </div>

                <div className="case-offer-body">
                  {isEditing ? (
                    <div className="case-offer-edit-form">
                      <div className="form-group">
                        <label>Precio Ofertado (Opcional)</label>
                        <div className="input-with-icon">
                          <DollarSign size={16} />
                          <input
                            type="number"
                            name="price"
                            step="0.01"
                            value={editData.price || ''}
                            onChange={handleInputChange}
                            placeholder="Ej. 1500.00"
                          />
                        </div>
                      </div>
                      <div className="form-group">
                        <label>Documento Fuente</label>
                        <input
                          type="text"
                          name="source_document"
                          value={editData.source_document || ''}
                          onChange={handleInputChange}
                          placeholder="Referencia o enlace"
                        />
                      </div>
                      <div className="form-group">
                        <label>Estado</label>
                        <select name="status" value={editData.status || offer.status} onChange={handleInputChange}>
                          <option value="PENDING">PENDING</option>
                          <option value="APPROVED">APPROVED</option>
                          <option value="OBSERVED">OBSERVED</option>
                          <option value="REJECTED">REJECTED</option>
                        </select>
                      </div>
                      <div className="edit-actions">
                        <Button type="button" variant="ghost" onClick={handleCancelEdit} disabled={isSubmitting}>
                          <X size={16} /> Cancelar
                        </Button>
                        <Button type="button" onClick={() => handleSaveOffer(offer.id)} disabled={isSubmitting}>
                          <Check size={16} /> {isSubmitting ? 'Guardando...' : 'Guardar'}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="case-offer-details">
                      <div className="detail-item price">
                        <span className="label">Precio:</span>
                        <span className="value">
                          {offer.price ? `$${offer.price.toFixed(2)}` : 'No especificado'}
                        </span>
                      </div>
                      <div className="detail-item">
                        <span className="label">Doc. Fuente:</span>
                        <span className="value">{offer.source_document || '-'}</span>
                      </div>
                      <div className="detail-item">
                        <span className="label">Estado Actual:</span>
                        <Badge variant={offer.status === 'APPROVED' ? 'success' : (offer.status === 'REJECTED' ? 'danger' : 'warning')}>
                          {offer.status}
                        </Badge>
                      </div>
                    </div>
                  )}
                </div>

                {!isEditing && (
                  <div className="case-offer-actions">
                    <Button variant="ghost" onClick={() => handleEditClick(offer)}>
                      <Edit2 size={16} /> Editar
                    </Button>
                    <Button variant="ghost" className="btn-delete" onClick={() => handleDeleteOffer(offer.id)}>
                      <Trash2 size={16} />
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
