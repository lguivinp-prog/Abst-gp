import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import apiClient from '../../../api/client';
import type { Section } from '../../../types';

interface SectionEditorProps {
  section: Section;
  onSave: (updatedSection: Section) => void;
  onCancel: () => void;
}

export const SectionEditor: React.FC<SectionEditorProps> = ({ section, onSave, onCancel }) => {
  const [text, setText] = useState(section.current_text || '');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSave = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await apiClient.put(`/cases/sections/${section.id}`, {
        is_selected: true,
        review_status: 'validated',
        current_text: text
      });
      onSave(res.data);
    } catch (err: any) {
      console.error('Error saving section:', err);
      setErrorMsg(err.response?.data?.detail || 'Error al guardar la sección');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50 w-[1000px] shadow-2xl">
      <CardHeader>
        <CardTitle>Editar: {section.title}</CardTitle>
      </CardHeader>
      <CardContent>
        {errorMsg && <div className="text-red-600 mb-4 text-sm bg-red-50 p-2 rounded">{errorMsg}</div>}
        
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <h3 className="font-semibold mb-2">Vista de Auditoría Técnica</h3>
            <div className="h-64 overflow-y-auto text-xs font-mono bg-slate-50 p-2 border rounded">
              <strong>Confianza:</strong> {section.confidence_score}<br/>
              <strong>Texto Original (Crudo):</strong><br/>{section.original_text}<br/><br/>
              <strong>Texto Limpiado (Técnico):</strong><br/>{section.cleaned_text}<br/><br/>
              <strong>Texto Normalizado (Agente):</strong><br/>{section.normalized_text}<br/><br/>
              <strong>Correcciones:</strong><br/>{JSON.stringify(section.corrections_json, null, 2)}<br/><br/>
              <strong>Advertencias:</strong><br/>{JSON.stringify(section.warnings_json, null, 2)}
            </div>
          </div>
          
          <div>
            <h3 className="font-semibold mb-2">Vista Contractual (Editable)</h3>
            <textarea
              className="w-full h-64 p-3 border rounded-md doc-paragraph focus:ring-2 focus:ring-blue-500"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
        </div>
        
        <div className="flex justify-between items-center">
          <div className="flex gap-2">
            <Button 
              variant="outline" 
              onClick={() => setText(section.original_text || '')}
              disabled={!section.original_text || text === section.original_text}
              title="Restaurar el texto original (OCR sin correcciones)"
            >
              Restaurar Original
            </Button>
            <Button 
              variant="outline" 
              onClick={() => setText(section.normalized_text || section.cleaned_text || section.original_text || '')}
              title="Aplicar sugerencias de limpieza y diccionario del agente"
            >
              Aceptar Correcciones
            </Button>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onCancel}>Cancelar</Button>
            <Button onClick={handleSave} disabled={loading}>{loading ? 'Guardando...' : 'Guardar'}</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
