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
        <Button onClick={onContinue}>Confirmar Secciones y Continuar</Button>
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
                  {sec.structure_json.map((block: StructureBlock, idx: number) => {
                    if (block.type === 'subsection_title') {
                      const level = block.level || 1;
                      const textSize = level === 1 ? 'text-xl' : level === 2 ? 'text-lg' : 'text-base';
                      const mt = level === 1 ? 'mt-6' : 'mt-4';
                      return <div key={idx} className={`${mt} mb-2 ${textSize}`}><strong>{block.label ? `${block.label} ` : ''}{block.text}</strong></div>;
                    }
                    if (block.type === 'paragraph') return <p key={idx} className="doc-paragraph">{block.text}</p>;
                    if (block.type === 'numbered_item') return <div key={idx} className="doc-paragraph" style={{ marginLeft: `${(block.level || 1) * 1.5}rem`, marginBottom: "0.5rem" }}><strong>{block.label}</strong> {block.text}</div>;
                    if (block.type === 'letter_item') return <div key={idx} className="doc-paragraph" style={{ marginLeft: "3rem", marginBottom: "0.5rem" }}><strong>{block.label}</strong> {block.text}</div>;
                    if (block.type === 'bullet_item') return <div key={idx} className="doc-paragraph" style={{ marginLeft: "3rem", marginBottom: "0.5rem" }}>- {block.text}</div>;
                    if (block.type === 'table_vertical') {
                      return (
                        <div key={idx} className="mb-4 overflow-x-auto">
                          <table className="w-full border-collapse border border-slate-300 text-sm">
                            <tbody>
                              {block.rows?.map((row, rIdx) => (
                                <React.Fragment key={rIdx}>
                                  {Object.entries(row).map(([k, v], cIdx) => (
                                    <tr key={cIdx}>
                                      <td className="border border-slate-300 bg-slate-100 p-2 font-bold w-1/3 align-top">{k}</td>
                                      <td className="border border-slate-300 p-2 align-top">
                                        {Array.isArray(v) ? (
                                          <ul className="list-disc ml-4">
                                            {v.map((item, iIdx) => <li key={iIdx}>{item}</li>)}
                                          </ul>
                                        ) : (
                                          <>{v as React.ReactNode}</>
                                        )}
                                      </td>
                                    </tr>
                                  ))}
                                </React.Fragment>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    }
                    if (block.type === 'warning') return <div key={idx} className="mb-2 p-2 bg-yellow-50 text-yellow-800 rounded border-l-4 border-yellow-500"><strong>Advertencia:</strong> {block.text}</div>;
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
