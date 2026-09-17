import React, { useState, useEffect, useMemo } from 'react';
import { Shield, AlertCircle, RefreshCw, Search } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { validationService } from '../../../api/v6/validation.service';
import type { ValidationRequestResponse } from '../../../api/v6/validation.types';
import { supplierService } from '../../../api/v6/supplier.service';
import type { CaseSupplierResponse } from '../../../api/v6/supplier.types';
import { AppError } from '../../../api/apiError';
import './CaseValidations.css';

import { ValidationSummaryBar } from './validations/ValidationSummaryBar';
import { SupplierValidationCard } from './validations/SupplierValidationCard';
import { CiiuDetailDrawer } from './validations/CiiuDetailDrawer';
import { getSupplierValidationSummary } from './validations/ValidationLogic';

interface CaseValidationsProps {
  caseId: string;
}

export const CaseValidations: React.FC<CaseValidationsProps> = ({ caseId }) => {
  const [validations, setValidations] = useState<ValidationRequestResponse[]>([]);
  const [suppliers, setSuppliers] = useState<CaseSupplierResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedSupplierId, setExpandedSupplierId] = useState<number | null>(null);

  // Drawer state
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [selectedCiiuData, setSelectedCiiuData] = useState<any>(null);

  // Filter & Search
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('ALL');

  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [valsData, supsData] = await Promise.all([
        validationService.getValidations(caseId),
        supplierService.getCaseSuppliers(caseId)
      ]);
      setValidations(valsData);
      setSuppliers(supsData);
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error inesperado al cargar las validaciones.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseId]);

  const handleRequestAllValidations = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      for (const sup of suppliers) {
        await validationService.createValidation(caseId, sup.id, { source: 'ALL' });
      }
      await loadData();
    } catch (err) {
      if (err instanceof AppError) setError(err.message);
      else setError('Error al orquestar validaciones.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Group validations by supplier
  const validationsBySupplier = useMemo(() => {
    const map: Record<number, ValidationRequestResponse[]> = {};
    suppliers.forEach(s => map[s.id] = []);
    validations.forEach(v => {
      if (map[v.supplier_id]) {
        map[v.supplier_id].push(v);
      } else {
        map[v.supplier_id] = [v];
      }
    });
    return map;
  }, [validations, suppliers]);

  const handleCiiuDetail = (ciiuData: any) => {
    setSelectedCiiuData(ciiuData);
    setIsDrawerOpen(true);
  };

  // Filter and Sort Suppliers
  const filteredAndSortedSuppliers = useMemo(() => {
    // Assign mapped statuses for filtering and sorting
    let filtered = suppliers.map(sup => {
      const vals = validationsBySupplier[sup.id] || [];
      const summary = getSupplierValidationSummary(vals);
      return { sup, summary };
    });

    if (filterStatus !== 'ALL') {
      filtered = filtered.filter(f => f.summary.status === filterStatus || (filterStatus === 'REVIEW' && f.summary.supplierNeedsReview));
    }

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(f =>
        (f.sup.business_name || '').toLowerCase().includes(term) ||
        (f.sup.ruc || '').includes(term)
      );
    }

    // Sort by status severity, then name
    filtered.sort((a, b) => {
      // Alerts first
      if (a.summary.supplierHasAlert && !b.summary.supplierHasAlert) return -1;
      if (!a.summary.supplierHasAlert && b.summary.supplierHasAlert) return 1;

      const rank = { 'REVIEW': 1, 'INCOMPLETE': 2, 'ERROR': 3, 'PENDING': 4, 'VALIDATED': 5, 'NO_DATA': 6 };
      const rankA = rank[a.summary.status as keyof typeof rank] || 99;
      const rankB = rank[b.summary.status as keyof typeof rank] || 99;
      if (rankA !== rankB) return rankA - rankB;
      return (a.sup.business_name || '').localeCompare(b.sup.business_name || '');
    });

    return filtered.map(item => item.sup);
  }, [suppliers, validationsBySupplier, searchTerm, filterStatus]);

  if (loading && validations.length === 0) {
    return (
      <div className="case-validations-loading">
        <div className="spinner"></div>
        <p>Cargando validaciones...</p>
      </div>
    );
  }

  return (
    <div className="case-validations-container max-w-[1400px] mx-auto px-6 pb-12">
      <div className="flex flex-col md:flex-row md:justify-between md:items-end border-b pb-4 mt-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 m-0">Validaciones de Proveedores</h2>
          <p className="text-sm text-gray-600 mt-1 mb-0">Consulte integraciones externas o registre verificaciones manuales con sustento.</p>
        </div>
        <div className="flex gap-2 mt-4 md:mt-0">
          <Button onClick={handleRequestAllValidations} disabled={isSubmitting || suppliers.length === 0} className="bg-blue-600 hover:bg-blue-700 text-white shadow-sm font-medium">
            {isSubmitting ? <><RefreshCw size={16} className="mr-2 spin" /> Ejecutando...</> : 'Ejecutar Validaciones Automáticas'}
          </Button>
          <Button variant="outline" className="font-medium bg-white shadow-sm">
            Nueva Validación Manual
          </Button>
        </div>
      </div>

      {error && (
        <div className="mt-4 bg-red-50 text-red-800 p-4 rounded-md border border-red-200 flex items-center">
          <AlertCircle size={16} className="mr-2" /> {error}
        </div>
      )}

      {suppliers.length > 0 && (
        <ValidationSummaryBar
          suppliers={suppliers}
          validationsBySupplier={validationsBySupplier}
        />
      )}

      <div className="val-toolbar">
        <div className="val-search-box">
          <Search size={16} className="val-search-icon" />
          <input
            type="text"
            placeholder="Buscar proveedor o RUC..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="val-search-input"
          />
        </div>
        <div className="val-filter-box">
          <span className="val-filter-label">Filtrar por:</span>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="val-filter-select"
          >
            <option value="ALL">Todos los proveedores</option>
            <option value="VALIDATED">Verificados</option>
            <option value="REVIEW">Requieren revisión</option>
            <option value="ALERTS">Con alertas</option>
            <option value="INCOMPLETE">No disponibles</option>
          </select>
        </div>
      </div>

      {filteredAndSortedSuppliers.length === 0 ? (
        <div className="case-validations-empty">
          <Shield size={48} className="empty-icon" />
          <h3>No se encontraron proveedores</h3>
          <p>Pruebe ajustando los filtros o términos de búsqueda.</p>
        </div>
      ) : (
        <div className="val-cards-container">
          {filteredAndSortedSuppliers.map(sup => (
            <SupplierValidationCard
              key={sup.id}
              supplier={sup}
              validations={validationsBySupplier[sup.id] || []}
              isExpanded={expandedSupplierId === sup.id}
              onToggle={() => setExpandedSupplierId(expandedSupplierId === sup.id ? null : sup.id)}
              onCiiuDetail={handleCiiuDetail}
            />
          ))}
        </div>
      )}

      <CiiuDetailDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        ciiuData={selectedCiiuData}
      />
    </div>
  );
};
