import React, { useState, useEffect } from 'react';
import { FileText, Building2, Check, X, AlertCircle, Trash2, Edit2 } from 'lucide-react';
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
  const [procurementItems, setProcurementItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingOfferId, setEditingOfferId] = useState<number | null>(null);
  const [editData, setEditData] = useState<SupplierOfferUpdate>({});
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadOffers = async () => {
    setLoading(true);
    setError(null);
    try {
      const { requirementsService } = await import('../../../api/v6/requirements.service');
      const [offersData, itemsData] = await Promise.all([
        offerService.getOffers(caseId),
        requirementsService.getProcurementItems(caseId)
      ]);
      setOffers(offersData);
      setProcurementItems(itemsData);
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

    // Initialize items from offer if present, or from procurementItems
    let initialItems = offer.items?.map(it => ({
      procurement_item_id: it.procurement_item_id,
      unit_price: it.unit_price
    }));

    if (!initialItems || initialItems.length === 0) {
      initialItems = procurementItems.map(pi => ({
        procurement_item_id: pi.id,
        unit_price: 0
      }));
    }

    setEditData({
      price: offer.price,
      currency: offer.currency || 'PEN',
      source_document: offer.source_document,
      status: offer.status,
      items: initialItems
    });
  };

  const handleCancelEdit = () => {
    setEditingOfferId(null);
    setEditData({});
    setSelectedFile(null);
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
      let documentIds: number[] | undefined = undefined;

      // If a file was selected, we should upload it first
      if (selectedFile) {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('document_type', 'oferta');

        const response = await fetch(`/api/v6/cases/${caseId}/documents`, {
          method: 'POST',
          body: formData,
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });

        if (response.ok) {
          const result = await response.json();
          documentIds = [result.id];
        } else {
          throw new Error('Error al subir documento de cotizaciÃ³n');
        }
      }

      const updateData = { ...editData };
      if (documentIds) updateData.document_ids = documentIds;

      await offerService.updateOffer(caseId, offerId, updateData);
      setEditingOfferId(null);
      setSelectedFile(null);
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
    if (!window.confirm('Â¿EstÃ¡ seguro de eliminar esta oferta?')) {
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
          <p>Primero debe vincular un proveedor en la pestaÃ±a "Proveedores".</p>
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
                      {procurementItems.length === 0 && (
                        <div className="form-group">
                          <label>Precio Ofertado (Opcional)</label>
                          <div className="input-with-icon">
                            <span className="text-gray-500 font-medium mr-2">
                              {(editData.currency || 'PEN') === 'USD' ? 'US$' : 'S/'}
                            </span>
                            <input
                              type="number"
                              name="price"
                              step="0.01"
                              value={editData.price || ''}
                              onChange={handleInputChange}
                              placeholder="Ej. 1500.00"
                            />
                            <select
                              name="currency"
                              value={editData.currency || 'PEN'}
                              onChange={handleInputChange}
                              className="ml-2 border rounded p-1"
                            >
                              <option value="PEN">PEN</option>
                              <option value="USD">USD</option>
                            </select>
                          </div>
                        </div>
                      )}
                      <div className="form-group mt-4">
                        <label>Ãtems Cotizados</label>
                        {procurementItems.some(pi => pi.status === 'REVIEW_REQUIRED' || pi.quantity === null || !pi.unit) ? (
                          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded relative" role="alert">
                            <strong className="font-bold">AcciÃ³n Requerida: </strong>
                            <span className="block sm:inline">Revise y complete los Ã­tems de contrataciÃ³n antes de registrar precios.</span>
                          </div>
                        ) : procurementItems.length > 0 ? (
                          <div className="border rounded overflow-hidden">
                            <table className="w-full text-sm">
                              <thead className="bg-gray-50 text-gray-700">
                                <tr>
                                  <th className="px-3 py-2 text-left font-medium">Ãtem</th>
                                  <th className="px-3 py-2 text-left font-medium">Cantidad</th>
                                  <th className="px-3 py-2 text-left font-medium">Unidad</th>
                                  <th className="px-3 py-2 text-left font-medium">Precio Unit.</th>
                                </tr>
                              </thead>
                              <tbody>
                                {procurementItems.map(pi => {
                                  const currentItem = editData.items?.find(it => it.procurement_item_id === pi.id);
                                  return (
                                    <tr key={pi.id} className="border-t border-gray-100">
                                      <td className="px-3 py-2">{pi.description}</td>
                                      <td className="px-3 py-2">{pi.quantity}</td>
                                      <td className="px-3 py-2">{pi.unit}</td>
                                      <td className="px-3 py-2">
                                        <input
                                          type="number"
                                          step="0.01"
                                          min="0"
                                          value={currentItem?.unit_price || ''}
                                          onChange={(e) => {
                                            const val = e.target.value ? parseFloat(e.target.value) : 0;
                                            setEditData(prev => ({
                                              ...prev,
                                              items: prev.items?.map(it =>
                                                it.procurement_item_id === pi.id
                                                  ? { ...it, unit_price: val }
                                                  : it
                                              )
                                            }));
                                          }}
                                          className="w-full border rounded p-1 text-right"
                                          placeholder="0.00"
                                        />
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <p className="text-sm text-gray-500 italic">No hay Ã­tems requeridos registrados.</p>
                        )}
                      </div>

                      <div className="form-group mt-4">
                        <label>Documento Fuente (CotizaciÃ³n)</label>
                        <input
                          type="file"
                          accept=".pdf"
                          onChange={e => {
                            if (e.target.files && e.target.files.length > 0) {
                              setSelectedFile(e.target.files[0]);
                            }
                          }}
                        />
                        {offer.documents && offer.documents.length > 0 && !selectedFile && (
                          <div className="text-xs text-green-600 mt-1">âœ“ Documento adjunto previamente</div>
                        )}
                      </div>
                      <div className="form-group">
                        <label>Estado</label>
                        <select name="status" value={editData.status || offer.status} onChange={handleInputChange}>
                          <option value="PENDING">PENDIENTE</option>
                          <option value="APPROVED">APROBADA</option>
                          <option value="OBSERVED">OBSERVADA</option>
                          <option value="REJECTED">RECHAZADA</option>
                        </select>
                      </div>
                      <div className="edit-actions">
                        <Button type="button" variant="ghost" onClick={handleCancelEdit} disabled={isSubmitting}>
                          <X size={16} /> Cancelar
                        </Button>
                        <Button type="button" onClick={() => handleSaveOffer(offer.id)} disabled={isSubmitting || procurementItems.some(pi => pi.status === 'REVIEW_REQUIRED' || pi.quantity === null || !pi.unit)}>
                          <Check size={16} /> {isSubmitting ? 'Guardando...' : 'Guardar'}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="case-offer-details">
                      <div className="detail-item price">
                        <span className="label">Precio:</span>
                        <span className="value">
                          {offer.price ? `${(offer.currency || 'PEN') === 'USD' ? 'US$' : 'S/'} ${offer.price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : 'No especificado'}
                        </span>
                      </div>
                      <div className="detail-item">
                        <span className="label">Doc. Fuente:</span>
                        <span className="value">{offer.source_document || '-'}</span>
                      </div>
                      <div className="detail-item">
                        <span className="label">Estado Actual:</span>
                        <Badge variant={offer.status === 'APPROVED' ? 'success' : (offer.status === 'REJECTED' ? 'danger' : 'warning')}>
                          {offer.status === 'PENDING' ? 'PENDIENTE' : offer.status === 'APPROVED' ? 'APROBADA' : offer.status === 'REJECTED' ? 'RECHAZADA' : 'OBSERVADA'}
                        </Badge>
                      </div>

                      {offer.items && offer.items.length > 0 && (
                        <div className="mt-4">
                          <h5 className="text-sm font-semibold text-gray-700 mb-2">Detalle de Ãtems</h5>
                          <div className="border rounded overflow-hidden">
                            <table className="w-full text-xs">
                              <thead className="bg-gray-50 text-gray-700">
                                <tr>
                                  <th className="px-2 py-1 text-left font-medium">Ãtem</th>
                                  <th className="px-2 py-1 text-right font-medium">Cant.</th>
                                  <th className="px-2 py-1 text-right font-medium">P. Unit</th>
                                  <th className="px-2 py-1 text-right font-medium">Subtotal</th>
                                </tr>
                              </thead>
                              <tbody>
                                {offer.items.map(it => (
                                  <tr key={it.id} className="border-t border-gray-100">
                                    <td className="px-2 py-1">{it.description || `Ãtem #${it.procurement_item_id}`}</td>
                                    <td className="px-2 py-1 text-right">{it.quantity} {it.unit}</td>
                                    <td className="px-2 py-1 text-right">{it.unit_price.toFixed(2)}</td>
                                    <td className="px-2 py-1 text-right font-medium">{it.subtotal.toFixed(2)}</td>
                                  </tr>
                                ))}
                                <tr className="border-t border-gray-200 bg-gray-50">
                                  <td colSpan={3} className="px-2 py-2 text-right font-semibold">Monto Total:</td>
                                  <td className="px-2 py-2 text-right font-bold text-green-700">
                                    {(offer.currency || 'PEN') === 'USD' ? 'US$' : 'S/'} {offer.total_amount?.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                                  </td>
                                </tr>
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
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
