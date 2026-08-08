import React, { useState } from 'react';
import { Button } from '../../../components/ui/Button';
import { AppError } from '../../../api/apiError';
import type { CaseCreate } from '../../../types';

interface CreateCaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CaseCreate) => Promise<void>;
}

export function CreateCaseModal({ isOpen, onClose, onSubmit }: CreateCaseModalProps) {
  const [title, setTitle] = useState('');
  const [contractType, setContractType] = useState('bienes');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!title.trim()) {
      setError('El título es obligatorio');
      return;
    }
    if (!contractType.trim()) {
      setError('El tipo de contrato es obligatorio');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload: CaseCreate = {
        title: title.trim(),
        contract_type: contractType
      };
      // Ejemplo de payload enviado: { title: "Licitación X", contract_type: "bienes" }
      await onSubmit(payload);
      setTitle('');
      setContractType('bienes');
      onClose();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Ocurrió un error inesperado al crear el caso');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex',
      justifyContent: 'center', alignItems: 'center', zIndex: 1000
    }}>
      <div style={{
        backgroundColor: 'white', padding: '2rem', borderRadius: '8px',
        width: '100%', maxWidth: '500px', boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
      }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '1.5rem' }}>Nuevo Caso</h2>
        
        {error && (
          <div style={{ backgroundColor: '#fee2e2', color: '#b91c1c', padding: '0.75rem', borderRadius: '4px', marginBottom: '1rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.875rem', fontWeight: 500 }}>Título *</label>
            <input 
              type="text" 
              name="title"
              value={title} 
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej: Licitación de Computadoras"
              style={{ padding: '0.75rem', border: '1px solid #ddd', borderRadius: '4px' }}
              disabled={isSubmitting}
            />
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.875rem', fontWeight: 500 }}>Tipo de Contrato *</label>
            <input
              type="text"
              name="contract_type"
              list="contract-types"
              value={contractType}
              onChange={(e) => setContractType(e.target.value)}
              style={{ padding: '0.75rem', border: '1px solid #ddd', borderRadius: '4px' }}
              disabled={isSubmitting}
            />
            <datalist id="contract-types">
              <option value="bienes">Bienes</option>
              <option value="servicios">Servicios</option>
              <option value="obras">Obras</option>
              <option value="Standard">Standard</option>
            </datalist>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1rem' }}>
            <Button type="button" variant="ghost" onClick={onClose} disabled={isSubmitting}>Cancelar</Button>
            <Button type="submit" variant="primary" disabled={isSubmitting || !title.trim()}>
              {isSubmitting ? 'Creando...' : 'Crear Caso'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
