import React, { useState, useEffect } from 'react';
import { Edit2, Save, X, Plus, AlertCircle, RefreshCw, Trash2 } from 'lucide-react';
import { requirementsService } from '../../../api/v6/requirements.service';
import type { RequirementResponse, RequirementUpdate, RequirementCreate, UpdateRequirementStatus } from '../../../api/v6/requirements.types';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { AppError } from '../../../api/apiError';

const UPDATE_STATUSES: UpdateRequirementStatus[] = [
  'VALIDATED',
  'MODIFIED_BY_USER',
  'OBSERVED',
  'REJECTED',
];

const isUpdateRequirementStatus = (value: string): value is UpdateRequirementStatus =>
  UPDATE_STATUSES.includes(value as UpdateRequirementStatus);

interface CaseRequirementsProps {
  caseId: string;
}

export const CaseRequirements: React.FC<CaseRequirementsProps> = ({ caseId }) => {
  const [requirements, setRequirements] = useState<RequirementResponse[]>([]);
  const [procurementItems, setProcurementItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<RequirementUpdate>({ status: 'VALIDATED', reason: '' });
  const [savingId, setSavingId] = useState<number | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState<RequirementCreate>({ requirement_type: '', description: '', mandatory: true });
  const [isAdding, setIsAdding] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [showAddItemForm, setShowAddItemForm] = useState(false);
  const [addItemForm, setAddItemForm] = useState({ item_number: '', description: '', quantity: 1, unit: 'UNIDAD' });
  const [isAddingItem, setIsAddingItem] = useState(false);
  const [itemFormError, setItemFormError] = useState<string | null>(null);

  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editItemForm, setEditItemForm] = useState({ item_number: '', description: '', quantity: 1, unit: 'UNIDAD' });

  const loadProcurementItems = async () => {
    try {
      const items = await requirementsService.getProcurementItems(caseId);
      setProcurementItems(items);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchRequirements = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await requirementsService.getRequirements(caseId);
      setRequirements(data);
      await loadProcurementItems();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error inesperado al cargar requerimientos.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    Promise.all([
      requirementsService.getRequirements(caseId),
      requirementsService.getProcurementItems(caseId)
    ])
      .then(([reqs, items]) => {
        if (mounted) {
          setRequirements(reqs);
          setProcurementItems(items);
          setLoading(false);
        }
      })
      .catch(err => {
        if (mounted) {
          if (err instanceof AppError) {
            setError(err.message);
          } else {
            setError('Error inesperado al cargar requerimientos.');
          }
          setLoading(false);
        }
      });
    return () => { mounted = false; };
  }, [caseId]);

  const handleStartEdit = (req: RequirementResponse) => {
    setMutationError(null);
    setEditingId(req.id);
    setEditForm({
      status: isUpdateRequirementStatus(req.status) ? req.status : 'VALIDATED',
      description: req.description,
      value: req.value,
      numeric_value: req.numeric_value,
      unit: req.unit,
      comparator: req.comparator,
      reason: ''
    });
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setMutationError(null);
  };

  const handleSaveEdit = async (id: number) => {
    setMutationError(null);
    if (!editForm.reason.trim()) {
      setMutationError('Debe ingresar un motivo para la modificación.');
      return;
    }

    setSavingId(id);
    try {
      await requirementsService.updateRequirement(caseId, id, editForm);
      await fetchRequirements();
      setEditingId(null);
    } catch (err) {
      if (err instanceof AppError) {
        setMutationError(`Error al guardar: ${err.message}`);
      } else {
        setMutationError('Error inesperado al guardar el requerimiento.');
      }
    } finally {
      setSavingId(null);
    }
  };

  const handleSaveNew = async () => {
    setFormError(null);
    if (!addForm.requirement_type.trim() || !addForm.description.trim()) {
      setFormError('El tipo de requerimiento y la descripción son obligatorios.');
      return;
    }

    setIsAdding(true);
    try {
      await requirementsService.createRequirement(caseId, addForm);
      await fetchRequirements();
      setShowAddForm(false);
      setAddForm({ requirement_type: '', description: '', mandatory: true });
    } catch (err) {
      if (err instanceof AppError) {
        setFormError(`Error al crear: ${err.message}`);
      } else {
        setFormError('Error inesperado al crear el requerimiento.');
      }
    } finally {
      setIsAdding(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PENDING_REVIEW': return <Badge variant="warning">Pendiente</Badge>;
      case 'VALIDATED': return <Badge variant="success">Validado</Badge>;
      case 'OBSERVED': return <Badge variant="danger">Observado</Badge>;
      case 'REJECTED': return <Badge variant="danger">Rechazado</Badge>;
      case 'MODIFIED_BY_USER': return <Badge variant="primary">Modificado</Badge>;
      default: return <Badge variant="secondary">{status}</Badge>;
    }
  };

  if (loading) {
    return (
      <div className="case-requirements">
        <div className="case-requirements__header">
          <h2 className="case-requirements__title">Requerimientos</h2>
          <p className="case-requirements__subtitle">Cargando requerimientos...</p>
        </div>
        <div className="case-requirements__loading">
          <div className="spinner"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="case-requirements">
        <div className="case-requirements__header">
          <h2 className="case-requirements__title">Requerimientos</h2>
          <p className="case-requirements__subtitle">Ocurrió un error al cargar la información.</p>
        </div>
        <div className="case-requirements__error">
          <div className="case-requirements__error-icon-wrapper">
            <AlertCircle size={20} />
            <span className="case-requirements__error-message">{error}</span>
          </div>
          <Button variant="outline" size="sm" onClick={fetchRequirements} leftIcon={<RefreshCw size={16} />}>
            Reintentar
          </Button>
        </div>
      </div>
    );
  }

  const handleSaveNewItem = async () => {
    setItemFormError(null);
    if (!addItemForm.description.trim()) {
      setItemFormError('La descripción es obligatoria.');
      return;
    }
    setIsAddingItem(true);
    try {
      await requirementsService.createProcurementItem(caseId, addItemForm);
      await loadProcurementItems();
      setShowAddItemForm(false);
      setAddItemForm({ item_number: '', description: '', quantity: 1, unit: 'UNIDAD' });
    } catch (err) {
      if (err instanceof AppError) {
        setItemFormError(err.message);
      } else {
        setItemFormError('Error al crear ítem.');
      }
    } finally {
      setIsAddingItem(false);
    }
  };

  const handleEditItem = async (itemId: number) => {
    setItemFormError(null);
    try {
      await requirementsService.updateProcurementItem(caseId, itemId, editItemForm);
      await loadProcurementItems();
      setEditingItemId(null);
    } catch (err) {
      if (err instanceof AppError) {
        setItemFormError(err.message);
      } else {
        setItemFormError('Error al actualizar ítem.');
      }
    }
  };

  const handleDeleteItem = async (itemId: number) => {
    if (!window.confirm('¿Está seguro de eliminar este ítem?')) return;
    try {
      await requirementsService.deleteProcurementItem(caseId, itemId);
      await loadProcurementItems();
    } catch (err) {
      alert('Error al eliminar ítem');
    }
  };

  const structuredReqs = requirements.filter(r => r.requirement_type !== 'CONTRACTUAL');
  const contractualReqs = requirements.filter(r => r.requirement_type === 'CONTRACTUAL');

  return (
    <div className="case-requirements">
      <div className="case-requirements__header-wrapper mt-4">
        <div className="case-requirements__header">
          <h2 className="case-requirements__title">Ítems de Contratación</h2>
          <p className="case-requirements__subtitle">
            Bienes o servicios económicos a cotizar.
          </p>
        </div>
        {!showAddItemForm && (
          <Button leftIcon={<Plus size={18} />} onClick={() => setShowAddItemForm(true)}>
            Agregar Ítem
          </Button>
        )}
      </div>

      <div className="case-requirements__list mb-6">
        {showAddItemForm && (
          <div className="case-requirements__card case-requirements__card--new">
            <h3 className="case-requirements__form-title">Nuevo Ítem</h3>
            {itemFormError && (
              <div className="case-requirements__mutation-error">
                <AlertCircle size={16} /> {itemFormError}
              </div>
            )}
            <div className="case-requirements__form">
              <div className="case-requirements__form-grid">
                <div className="case-requirements__field">
                  <label className="case-requirements__label">Descripción</label>
                  <input
                    type="text"
                    className="case-requirements__input"
                    value={addItemForm.description}
                    onChange={e => setAddItemForm({...addItemForm, description: e.target.value})}
                    disabled={isAddingItem}
                  />
                </div>
                <div className="case-requirements__field">
                  <label className="case-requirements__label">Cantidad</label>
                  <input
                    type="number"
                    className="case-requirements__input"
                    value={addItemForm.quantity}
                    onChange={e => setAddItemForm({...addItemForm, quantity: parseFloat(e.target.value) || 0})}
                    disabled={isAddingItem}
                  />
                </div>
                <div className="case-requirements__field">
                  <label className="case-requirements__label">Unidad</label>
                  <input
                    type="text"
                    className="case-requirements__input"
                    value={addItemForm.unit}
                    onChange={e => setAddItemForm({...addItemForm, unit: e.target.value})}
                    disabled={isAddingItem}
                  />
                </div>
              </div>
              <div className="case-requirements__edit-actions mt-2">
                <Button variant="outline" size="sm" onClick={() => setShowAddItemForm(false)} disabled={isAddingItem}>
                  Cancelar
                </Button>
                <Button size="sm" onClick={handleSaveNewItem} disabled={isAddingItem || !addItemForm.description.trim()}>
                  Guardar
                </Button>
              </div>
            </div>
          </div>
        )}

        {procurementItems.length === 0 && !showAddItemForm ? (
          <div className="case-requirements__card case-requirements__empty">
            <p>No hay ítems de contratación registrados.</p>
          </div>
        ) : (
          procurementItems.map(item => (
            <div key={item.id} className="case-requirements__card">
              {editingItemId === item.id ? (
                <div className="case-requirements__form">
                  <div className="case-requirements__form-grid">
                    <div className="case-requirements__field">
                      <label className="case-requirements__label">Descripción</label>
                      <input
                        type="text"
                        className="case-requirements__input"
                        value={editItemForm.description}
                        onChange={e => setEditItemForm({...editItemForm, description: e.target.value})}
                      />
                    </div>
                    <div className="case-requirements__field">
                      <label className="case-requirements__label">Cantidad</label>
                      <input
                        type="number"
                        className="case-requirements__input"
                        value={editItemForm.quantity}
                        onChange={e => setEditItemForm({...editItemForm, quantity: parseFloat(e.target.value) || 0})}
                      />
                    </div>
                    <div className="case-requirements__field">
                      <label className="case-requirements__label">Unidad</label>
                      <input
                        type="text"
                        className="case-requirements__input"
                        value={editItemForm.unit}
                        onChange={e => setEditItemForm({...editItemForm, unit: e.target.value})}
                      />
                    </div>
                  </div>
                  <div className="case-requirements__edit-actions mt-2">
                    <Button variant="outline" size="sm" onClick={() => setEditingItemId(null)}>
                      Cancelar
                    </Button>
                    <Button size="sm" onClick={() => handleEditItem(item.id)}>
                      Guardar
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="case-requirements__status-row">
                  <div className="case-requirements__requirement-meta flex items-center gap-2">
                    {item.status === 'REVIEW_REQUIRED' && (
                      <Badge variant="danger">REQUIERE REVISIÓN</Badge>
                    )}
                    {item.status === 'VALIDATED' && (
                      <Badge variant="success">VALIDATED</Badge>
                    )}
                    <p className="case-requirements__description">
                      <strong>{item.quantity !== null ? item.quantity : '?'} {item.unit || 'POR DEFINIR'}</strong> - {item.description}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => {
                      setEditingItemId(item.id);
                      setEditItemForm({
                        item_number: item.item_number || '',
                        description: item.description,
                        quantity: item.quantity !== null ? item.quantity : 1,
                        unit: item.unit || 'UNIDAD',
                        status: 'VALIDATED'
                      } as any);
                    }}>
                      <Edit2 size={16} />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDeleteItem(item.id)}>
                      <Trash2 size={16} className="text-red-500" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="case-requirements__header-wrapper mt-8">
        <div className="case-requirements__header">
          <h2 className="case-requirements__title">Condiciones Contractuales del Requerimiento</h2>
          <p className="case-requirements__subtitle">
            Condiciones extraídas automáticamente (Plazo, Garantía, Vida Útil, etc.)
          </p>
        </div>
      </div>

      <div className="case-requirements__list mb-6">
        {contractualReqs.length === 0 ? (
          <div className="case-requirements__card case-requirements__empty">
            <p>No se han identificado condiciones contractuales.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left border-collapse">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="p-3 font-semibold">Condición</th>
                  <th className="p-3 font-semibold">Valor</th>
                  <th className="p-3 font-semibold">Regla</th>
                  <th className="p-3 font-semibold">Fuente</th>
                  <th className="p-3 font-semibold">Página</th>
                  <th className="p-3 font-semibold">Confianza</th>
                  <th className="p-3 font-semibold">Estado</th>
                  <th className="p-3 font-semibold">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {contractualReqs.map(req => {
                  const ev = req.evidences?.[0];
                  return (
                    <tr key={req.id}>
                      <td className="p-3">{req.description}</td>
                      <td className="p-3">{req.numeric_value !== null ? `${req.numeric_value} ${req.unit || ''}` : req.value}</td>
                      <td className="p-3">{req.comparator || 'N/A'}</td>
                      <td className="p-3 text-gray-500">{ev?.source_document || 'N/A'}</td>
                      <td className="p-3 text-gray-500">{ev?.source_page || 'N/A'}</td>
                      <td className="p-3">{ev?.confidence ? `${(ev.confidence * 100).toFixed(0)}%` : 'N/A'}</td>
                      <td className="p-3">{getStatusBadge(req.status)}</td>
                      <td className="p-3">
                        <Button variant="ghost" size="sm" onClick={() => handleStartEdit(req)}>
                          <Edit2 size={16} />
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="case-requirements__header-wrapper">
        <div className="case-requirements__header">
          <h2 className="case-requirements__title">Requerimientos Estructurados</h2>
          <p className="case-requirements__subtitle">
            Revisión y estructuración de las condiciones extraídas del documento de requerimiento.
          </p>
        </div>
        {!showAddForm && (
          <Button leftIcon={<Plus size={18} />} onClick={() => setShowAddForm(true)}>
            Agregar Requerimiento
          </Button>
        )}
      </div>

      <div className="case-requirements__list">
        {showAddForm && (
          <div className="case-requirements__card case-requirements__card--new">
            <h3 className="case-requirements__form-title">Nuevo Requerimiento Manual</h3>
            {formError && (
              <div className="case-requirements__mutation-error">
                <AlertCircle size={16} /> {formError}
              </div>
            )}
            <div className="case-requirements__form">
              <div className="case-requirements__form-grid">
                <div className="case-requirements__field">
                  <label className="case-requirements__label">Tipo de requerimiento</label>
                  <input
                    type="text"
                    className="case-requirements__input"
                    value={addForm.requirement_type}
                    onChange={e => setAddForm({...addForm, requirement_type: e.target.value})}
                    disabled={isAdding}
                    placeholder="Ej: Especificaciones Técnicas"
                  />
                </div>
                <div className="case-requirements__field">
                  <label className="case-requirements__label">Obligatoriedad</label>
                  <select
                    className="case-requirements__input"
                    value={addForm.mandatory ? 'true' : 'false'}
                    onChange={e => setAddForm({...addForm, mandatory: e.target.value === 'true'})}
                    disabled={isAdding}
                  >
                    <option value="true">Obligatorio</option>
                    <option value="false">Opcional</option>
                  </select>
                </div>
              </div>
              <div className="case-requirements__field">
                <label className="case-requirements__label">Descripción</label>
                <textarea
                  className="case-requirements__input case-requirements__input--textarea"
                  rows={2}
                  value={addForm.description}
                  onChange={e => setAddForm({...addForm, description: e.target.value})}
                  disabled={isAdding}
                />
              </div>
              <div className="case-requirements__field">
                <label className="case-requirements__label">Valor / Umbral (Opcional)</label>
                <input
                  type="text"
                  className="case-requirements__input"
                  value={addForm.value || ''}
                  onChange={e => setAddForm({...addForm, value: e.target.value})}
                  disabled={isAdding}
                />
              </div>
              <div className="case-requirements__edit-actions">
                <Button variant="outline" size="sm" onClick={() => setShowAddForm(false)} disabled={isAdding}>
                  Cancelar
                </Button>
                <Button size="sm" onClick={handleSaveNew} disabled={isAdding || !addForm.requirement_type.trim() || !addForm.description.trim()}>
                  {isAdding ? 'Guardando...' : 'Guardar Nuevo'}
                </Button>
              </div>
            </div>
          </div>
        )}

        {structuredReqs.length === 0 && !showAddForm ? (
          <div className="case-requirements__card case-requirements__empty">
            <p>No se han identificado requerimientos estructurados para este expediente.</p>
          </div>
        ) : (
          structuredReqs.map(req => (
            <div key={req.id} className="case-requirements__card">
              {editingId === req.id ? (
                <div className="case-requirements__form">
                  <div className="case-requirements__form-header">
                    <span className="case-requirements__form-title-small">Editando Requerimiento #{req.id}</span>
                  </div>
                  {mutationError && (
                    <div className="case-requirements__mutation-error">
                      <AlertCircle size={16} /> {mutationError}
                    </div>
                  )}
                  <div className="case-requirements__form-grid">
                    <div className="case-requirements__field">
                      <label className="case-requirements__label">Estado</label>
                      <select
                        className="case-requirements__input"
                        value={editForm.status}
                        onChange={e => {
                          const val = e.target.value;
                          if (isUpdateRequirementStatus(val)) {
                            setEditForm({...editForm, status: val});
                          }
                        }}
                        disabled={savingId === req.id}
                      >
                        <option value="VALIDATED">Validado</option>
                        <option value="MODIFIED_BY_USER">Modificado por Usuario</option>
                        <option value="OBSERVED">Observado</option>
                        <option value="REJECTED">Rechazado</option>
                      </select>
                    </div>
                    <div className="case-requirements__field">
                      <label className="case-requirements__label">Motivo del Cambio (Obligatorio)</label>
                      <input
                        type="text"
                        className="case-requirements__input"
                        value={editForm.reason}
                        onChange={e => setEditForm({...editForm, reason: e.target.value})}
                        disabled={savingId === req.id}
                        placeholder="Ej: Corrección manual..."
                      />
                    </div>
                  </div>
                  <div className="case-requirements__field">
                    <label className="case-requirements__label">Descripción</label>
                    <textarea
                      className="case-requirements__input case-requirements__input--textarea"
                      rows={2}
                      value={editForm.description || ''}
                      onChange={e => setEditForm({...editForm, description: e.target.value})}
                      disabled={savingId === req.id}
                    />
                  </div>
                  <div className="case-requirements__field">
                    <label className="case-requirements__label">Valor / Umbral</label>
                    <input
                      type="text"
                      className="case-requirements__input"
                      value={editForm.value || ''}
                      onChange={e => setEditForm({...editForm, value: e.target.value})}
                      disabled={savingId === req.id}
                    />
                  </div>

                  <div className="case-requirements__field">
                    <label className="case-requirements__label">Valor numérico</label>
                    <input
                      type="number"
                      className="case-requirements__input"
                      value={editForm.numeric_value || ''}
                      onChange={e => setEditForm({...editForm, numeric_value: parseFloat(e.target.value)})}
                      disabled={savingId === req.id}
                    />
                  </div>
                  <div className="case-requirements__field">
                    <label className="case-requirements__label">Unidad</label>
                    <input
                      type="text"
                      className="case-requirements__input"
                      value={editForm.unit || ''}
                      onChange={e => setEditForm({...editForm, unit: e.target.value})}
                      disabled={savingId === req.id}
                    />
                  </div>
                  <div className="case-requirements__field">
                    <label className="case-requirements__label">Regla (Comparator)</label>
                    <select
                      className="case-requirements__input"
                      value={editForm.comparator || ''}
                      onChange={e => setEditForm({...editForm, comparator: e.target.value})}
                      disabled={savingId === req.id}
                    >
                      <option value="">Seleccionar...</option>
                      <option value="MIN">Mínimo (MIN)</option>
                      <option value="MAX">Máximo (MAX)</option>
                      <option value="EXACT">Exacto (EXACT)</option>
                      <option value="RANGE">Rango (RANGE)</option>
                    </select>
                  </div>

                  <div className="case-requirements__edit-actions">
                    <Button variant="outline" size="sm" onClick={handleCancelEdit} disabled={savingId === req.id}>
                      <X size={16} className="mr-1" /> Cancelar
                    </Button>
                    <Button size="sm" onClick={() => handleSaveEdit(req.id)} disabled={savingId === req.id || !editForm.reason.trim()}>
                      <Save size={16} className="mr-1" /> {savingId === req.id ? 'Guardando...' : 'Guardar'}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="case-requirements__status-row">
                  <div className="case-requirements__requirement-meta">
                    <div className="case-requirements__badge-group">
                      <span className="case-requirements__type-badge">{req.requirement_type}</span>
                      {getStatusBadge(req.status)}
                      {req.mandatory ? (
                        <Badge variant="secondary">Obligatorio</Badge>
                      ) : (
                        <Badge variant="secondary">Opcional</Badge>
                      )}
                    </div>
                    <p className="case-requirements__description">{req.description}</p>
                    {req.value && (
                      <p className="case-requirements__value-display"><span>Valor:</span> {req.value}</p>
                    )}
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => handleStartEdit(req)}>
                    <Edit2 size={16} />
                  </Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
