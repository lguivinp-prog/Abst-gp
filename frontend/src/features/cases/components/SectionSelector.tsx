import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import type { Section, StructureBlock } from '../../../types';


interface SectionSelectorProps {
  sections: Section[];
  onEditSection: (section: Section) => void;
  onContinue: () => void;
}

export const SectionSelector: React.FC<SectionSelectorProps> = ({ sections, onEditSection, onContinue }) => {
  return (
    <div className="sections-container">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Secciones Detectadas (Revisión)</h2>
        <Button 
          onClick={onContinue}
          disabled={sections.some(s => s.review_status !== 'validated')}
          title={sections.some(s => s.review_status !== 'validated') ? "Debe validar todas las secciones antes de continuar" : ""}
        >
          Confirmar Secciones y Continuar
        </Button>
      </div>
      
      <div className="grid gap-4">
        {sections.map((sec) => (
          <Card key={sec.id}>
            <CardHeader className="flex flex-row justify-between items-center">
              <CardTitle className="text-md">
                {sec.original_roman ? `${sec.original_roman}. ` : ''}{sec.title}
              </CardTitle>
              <div className="flex gap-2">
                <Badge variant={sec.review_status === 'validated' ? 'success' : 'warning'}>
                  {sec.review_status === 'validated' ? 'Validada' : 'Pendiente Revisión'}
                </Badge>
                <Button variant="outline" onClick={() => onEditSection(sec)}>Editar</Button>
              </div>
            </CardHeader>
            <CardContent>
              {sec.structure_json && sec.structure_json.length > 0 ? (
                <div className="text-gray-900 text-lg">
                  {sec.structure_json.map((block: any, idx: number) => {
                    if (block.type === 'HEADING' || block.type === 'subsection_title' || block.type === 'section_title') {
                      return <div key={idx} className={`mt-6 mb-2 text-xl`}><strong>{block.label ? `${block.label} ` : ''}{block.text}</strong></div>;
                    }
                    if (block.type === 'PARAGRAPH' || block.type === 'paragraph') {
                      return <p key={idx} className="doc-paragraph">{block.text}</p>;
                    }
                    if (block.type === 'LIST_ITEM' || block.type === 'bullet_item' || block.type === 'letter_item' || block.type === 'numbered_item') {
                      return <div key={idx} className="doc-paragraph" style={{ marginLeft: "2rem", marginBottom: "0.5rem" }}>{block.text}</div>;
                    }
                    if (block.type === 'TABLE' || block.type === 'table_vertical') {
                      return (
                        <div key={idx} className="mb-4 overflow-x-auto">
                          {block.table_data ? (
                            <table className="w-full border-collapse border border-slate-300 text-sm">
                              <tbody>
                                {block.table_data.rows?.map((row: any, rIdx: number) => (
                                  <tr key={rIdx}>
                                    {row.cells?.map((cell: any, cIdx: number) => (
                                      <td key={cIdx} className="border border-slate-300 p-2 align-top">{cell.text}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <div className="p-4 bg-gray-100 border border-gray-300 rounded text-center">
                              <em>Tabla detectada pero sin estructura tabular renderizable. {block.text}</em>
                            </div>
                          )}
                          {block.manual_required && (
                            <div className="text-xs text-red-600 mt-1">⚠️ Esta tabla requiere revisión manual.</div>
                          )}
                        </div>
                      );
                    }
                    if (block.type === 'FORMULA_OR_LAYOUT_BLOCK') {
                      return (
                        <div key={idx} className="my-4 p-4 bg-slate-50 border border-slate-200 rounded text-center font-mono text-sm whitespace-pre-wrap">
                          {block.text}
                        </div>
                      );
                    }
                    if (block.type === 'warning') {
                      return <div key={idx} className="mb-2 p-2 bg-yellow-50 text-yellow-800 rounded border-l-4 border-yellow-500"><strong>Advertencia:</strong> {block.text}</div>;
                    }
                    return <p key={idx} className="doc-paragraph">{block.text}</p>;
                  })}
                </div>
              ) : (
                <div className="text-gray-900 text-lg">
                  {sec.current_text?.split('\n').map((line, idx) => (
                    line.trim() ? <p key={idx} className="doc-paragraph">{line}</p> : null
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};
