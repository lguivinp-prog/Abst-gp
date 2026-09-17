import React, { useEffect } from 'react';
import { X, ExternalLink } from 'lucide-react';
interface CiiuDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  ciiuData: any;
}

export const CiiuDetailDrawer: React.FC<CiiuDetailDrawerProps> = ({ isOpen, onClose, ciiuData }) => {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEsc);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen || !ciiuData) return null;

  return (
    <>
      <div
        className="val-drawer-overlay"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`val-drawer ${isOpen ? 'val-drawer-open' : ''}`}
        role="dialog"
        aria-modal="true"
      >
        <div className="val-drawer-header">
          <div>
            <h2 className="val-drawer-title">Detalle Oficial INEI</h2>
          </div>
          <button
            onClick={onClose}
            className="val-drawer-close"
            aria-label="Cerrar detalle"
          >
            <X size={20} />
          </button>
        </div>

        <div className="val-drawer-body">
          <div className="val-drawer-section" style={{ borderBottom: '1px solid #e5e7eb', paddingBottom: '16px' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 900, color: '#111827', marginBottom: '8px' }}>
              CIIU REV. 4 — {ciiuData.codigo_ciiu || "SIN CÓDIGO"}
            </h3>
            <p style={{ fontSize: '1.125rem', color: '#374151', margin: 0, lineHeight: 1.2 }}>
              {ciiuData.descripcion_inei || "Denominación no disponible"}
            </p>
          </div>

          <div>
            <div className="val-drawer-section">
              <p style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>Tipo</p>
              <span className="val-badge val-secondary">{ciiuData.tipo || "ACTIVIDAD"}</span>
            </div>

            <div className="val-drawer-section">
              <p style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>Actividad registrada (SUNAT)</p>
              <p style={{ fontSize: '0.875rem', color: '#1f2937', margin: 0, backgroundColor: '#f9fafb', padding: '12px', borderRadius: '4px', border: '1px solid #f3f4f6' }}>
                {ciiuData.actividad_sunat || "No disponible"}
              </p>
            </div>

            {ciiuData.codigo_ciiu && (
              <>
                <div className="val-drawer-section">
                  <p style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>Descripción Oficial</p>
                  <p style={{ fontSize: '0.875rem', color: '#1f2937', margin: 0, lineHeight: 1.6, textAlign: 'justify' }}>
                    {ciiuData.descripcion_inei || "Sin descripción"}
                  </p>
                </div>

                <div className="val-drawer-section">
                  <p style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>Incluye</p>
                  <div style={{ fontSize: '0.875rem', color: '#1f2937', margin: 0, lineHeight: 1.6, whiteSpace: 'pre-wrap', textAlign: 'justify', backgroundColor: '#eff6ff', padding: '16px', borderRadius: '6px', border: '1px solid #dbeafe' }}>
                    {ciiuData.incluye ? ciiuData.incluye : <span style={{ color: '#6b7280', fontStyle: 'italic' }}>Sin información específica publicada en este campo.</span>}
                  </div>
                </div>

                <div className="val-drawer-section">
                  <p style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginBottom: '4px' }}>No Incluye</p>
                  <div style={{ fontSize: '0.875rem', color: '#1f2937', margin: 0, lineHeight: 1.6, whiteSpace: 'pre-wrap', textAlign: 'justify', backgroundColor: '#f9fafb', padding: '16px', borderRadius: '6px', border: '1px solid #e5e7eb' }}>
                    {ciiuData.no_incluye ? ciiuData.no_incluye : <span style={{ color: '#6b7280', fontStyle: 'italic' }}>Sin información específica publicada en este campo.</span>}
                  </div>
                </div>

                {ciiuData.detail_status === 'UNAVAILABLE' && (
                  <div className="val-drawer-section" style={{ backgroundColor: '#fffbeb', border: '1px solid #fde68a', borderRadius: '4px', padding: '12px' }}>
                    <p style={{ fontSize: '0.875rem', color: '#92400e', fontStyle: 'italic', margin: 0, fontWeight: 500 }}>Detalle oficial INEI temporalmente no disponible desde la fuente original.</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {ciiuData.inei_detail_url && (
          <div style={{ padding: '16px', borderTop: '1px solid #e5e7eb', backgroundColor: '#f9fafb', display: 'flex', justifyContent: 'flex-end' }}>
            <a
              href={ciiuData.inei_detail_url}
              target="_blank"
              rel="noopener noreferrer"
              className="val-drawer-link-btn"
              style={{ backgroundColor: '#2563eb', color: 'white', borderColor: '#2563eb' }}
            >
              <ExternalLink size={16} />
              ABRIR FICHA OFICIAL INEI
            </a>
          </div>
        )}
      </div>
    </>
  );
};
