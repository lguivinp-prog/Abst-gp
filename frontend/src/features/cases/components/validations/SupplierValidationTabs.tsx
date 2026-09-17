import React, { useState } from 'react';
import { Badge } from '../../../../components/ui/Badge';
import { ValidationStatusBadge } from './ValidationStatusBadge';
import { ExternalLink, AlertTriangle } from 'lucide-react';

interface SupplierValidationTabsProps {
  supplier: any;
  validations: any[];
  onCiiuDetail: (ciiuData: any) => void;
}

export const SupplierValidationTabs: React.FC<SupplierValidationTabsProps> = ({ supplier, validations, onCiiuDetail }) => {
  const [activeTab, setActiveTab] = useState('resumen');

  const sunatVal = validations.find(v => v.source === 'SUNAT');
  const migoVal = validations.find(v => v.source === 'MIGO_ACTIVITIES');
  const ciiuVal = validations.find(v => v.source === 'CIIU');
  const rnpVal = validations.find(v => v.source === 'RNP');
  const fupVal = validations.find(v => v.source === 'FUP');

  const manualValidations = validations.filter(v => v.validation_mode === 'MANUAL');
  const hasMismatch = migoVal?.response_payload?.cross_source_consistency === false;

  const tabs = [
    { id: 'resumen', label: 'Resumen' },
    { id: 'sunat', label: 'SUNAT' },
    { id: 'actividades', label: 'Actividades' },
    { id: 'ciiu', label: 'CIIU' },
    { id: 'rnp_fup', label: 'RNP / FUP' },
    { id: 'manuales', label: 'Manuales' },
    { id: 'historial', label: 'Historial' }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="val-tabs-header">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`val-tab-btn ${activeTab === tab.id ? 'val-tab-active' : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="p-6 bg-white min-h-[300px]">
        {activeTab === 'resumen' && (
          <div className="grid grid-cols-2 gap-y-4 gap-x-8 max-w-3xl">
            <div><span className="text-xs font-bold text-gray-500 uppercase">RUC</span><p className="m-0 text-sm">{supplier.ruc}</p></div>
            <div><span className="text-xs font-bold text-gray-500 uppercase">Razón Social</span><p className="m-0 text-sm font-medium">{supplier.business_name || '-'}</p></div>
            <div><span className="text-xs font-bold text-gray-500 uppercase">Estado SUNAT</span><p className="m-0 text-sm">{sunatVal?.response_payload?.estado || '-'} / {sunatVal?.response_payload?.condicion || '-'}</p></div>
            <div><span className="text-xs font-bold text-gray-500 uppercase">Actividades</span><p className="m-0 text-sm">{migoVal?.response_payload?.activities?.length || 0} registradas</p></div>
            <div><span className="text-xs font-bold text-gray-500 uppercase">CIIU</span><p className="m-0 text-sm">{ciiuVal?.response_payload?.results?.length || 0} verificadas</p></div>
            <div><span className="text-xs font-bold text-gray-500 uppercase">RNP</span><p className="m-0 text-sm">{rnpVal?.response_payload?.registro || 'No disponible'}</p></div>
            <div><span className="text-xs font-bold text-gray-500 uppercase">FUP</span><p className="m-0 text-sm">{fupVal?.status === 'PASSED' ? 'OK' : 'No disponible'}</p></div>
            <div>
              <span className="text-xs font-bold text-gray-500 uppercase">Alertas</span>
              <p className="m-0 text-sm text-amber-700 font-medium">
                {hasMismatch ? '1 diferencia entre fuentes' : 'Ninguna'}
              </p>
            </div>
          </div>
        )}

        {activeTab === 'sunat' && (
          <div className="max-w-4xl">
            <div className="grid grid-cols-2 gap-y-4 gap-x-8 mb-6">
              <div><span className="text-xs font-bold text-gray-500 uppercase">RUC</span><p className="m-0 text-sm">{supplier.ruc}</p></div>
              <div><span className="text-xs font-bold text-gray-500 uppercase">Razón Social</span><p className="m-0 text-sm">{sunatVal?.response_payload?.razon_social || '-'}</p></div>
              <div><span className="text-xs font-bold text-gray-500 uppercase">Estado</span><p className="m-0 text-sm">{sunatVal?.response_payload?.estado || '-'}</p></div>
              <div><span className="text-xs font-bold text-gray-500 uppercase">Condición</span><p className="m-0 text-sm">{sunatVal?.response_payload?.condicion || '-'}</p></div>
              <div className="col-span-2"><span className="text-xs font-bold text-gray-500 uppercase">Domicilio</span><p className="m-0 text-sm">{sunatVal?.response_payload?.domicilio || '-'}</p></div>
              <div className="col-span-2"><span className="text-xs font-bold text-gray-500 uppercase">Actividad reportada en consulta RUC</span><p className="m-0 text-sm font-medium">{sunatVal?.response_payload?.actividad_reportada_decolecta || '-'}</p></div>
            </div>

            <div className="flex items-center gap-3 mb-6">
              <Badge variant="success">VALIDADO</Badge>
              <span className="text-xs text-gray-500">Consulta SUNAT vía {sunatVal?.response_payload?.integration_provider || 'Decolecta'}</span>
            </div>

            <a href="https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias" target="_blank" rel="noopener noreferrer" className="text-xs bg-gray-100 border border-gray-300 hover:bg-gray-200 text-gray-800 px-4 py-2 rounded inline-flex items-center no-underline font-medium transition-colors">
              Abrir consulta oficial SUNAT <ExternalLink size={14} className="ml-2" />
            </a>

            {hasMismatch && (
              <div className="mt-6 bg-amber-50 border-l-4 border-amber-400 p-4 rounded-r">
                <h4 className="text-sm font-bold text-amber-800 mb-1 flex items-center gap-2">
                  <AlertTriangle size={16} /> DIFERENCIA ENTRE FUENTES CONSULTADAS
                </h4>
                <p className="text-sm text-amber-700 m-0">
                  La actividad reportada en la consulta RUC no coincide con las actividades registradas en la consulta de actividades económicas.
                </p>
                <button onClick={() => setActiveTab('actividades')} className="mt-3 text-xs bg-white border border-amber-300 text-amber-800 px-3 py-1.5 rounded font-medium hover:bg-amber-100 transition-colors cursor-pointer">
                  Ver diferencia
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'actividades' && (
          <div>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-gray-800 uppercase m-0">Actividades Económicas Registradas</h4>
                <p className="text-xs text-gray-500 m-0">{migoVal?.response_payload?.activities?.length || 0} actividades encontradas</p>
              </div>
            </div>

            {migoVal?.response_payload?.activities && migoVal.response_payload.activities.length > 0 ? (
              <div className="val-table-container">
                <table className="val-table">
                  <thead>
                    <tr>
                      <th style={{ width: '40px', textAlign: 'center' }}>#</th>
                      <th style={{ width: '100px' }}>Tipo</th>
                      <th style={{ width: '100px' }}>Código</th>
                      <th>Descripción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {migoVal.response_payload.activities.map((act: any, idx: number) => (
                      <tr key={idx}>
                        <td style={{ textAlign: 'center' }}>{idx + 1}</td>
                        <td><span className="val-badge val-secondary">{act.tipo}</span></td>
                        <td style={{ fontFamily: 'monospace' }}>{act.codigo_reportado || '-'}</td>
                        <td style={{ fontWeight: 500 }}>{act.descripcion_sunat}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-500 italic">No se encontraron actividades.</p>
            )}

            {hasMismatch && (
              <div className="mt-6 bg-amber-50 border-l-4 border-amber-400 p-4 rounded-r">
                <h4 className="text-sm font-bold text-amber-800 mb-2">Diferencia entre fuentes consultadas</h4>
                <p className="text-sm text-amber-700 mb-4">
                  La actividad reportada en la consulta RUC no coincide con ninguna de las actividades obtenidas en la consulta de actividades.
                </p>
                <div className="bg-white p-3 rounded border border-amber-200">
                  <p className="text-xs font-bold text-gray-500 uppercase mb-1">Actividad reportada en consulta RUC:</p>
                  <p className="text-sm mb-3 font-medium">{migoVal.response_payload?.decolecta_ciiu_result?.actividad_sunat || "Actividad no disponible"}</p>

                  <p className="text-xs font-bold text-gray-500 uppercase mb-1">Código CIIU identificado:</p>
                  <p className="text-sm mb-4 font-mono">{migoVal.response_payload?.decolecta_ciiu_result?.codigo_ciiu || "No identificado"}</p>

                  <div className="flex gap-2">
                    {migoVal.response_payload?.decolecta_ciiu_result && (
                      <button
                        onClick={() => onCiiuDetail(migoVal.response_payload.decolecta_ciiu_result)}
                        className="text-xs bg-amber-100 hover:bg-amber-200 text-amber-800 px-3 py-1.5 rounded inline-flex items-center font-medium border border-amber-300 transition-colors cursor-pointer"
                      >
                        Ver clasificación CIIU
                      </button>
                    )}
                    <a href="https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias" target="_blank" rel="noopener noreferrer" className="text-xs bg-white hover:bg-gray-50 text-gray-800 px-3 py-1.5 rounded inline-flex items-center no-underline font-medium border border-gray-300 transition-colors">
                      Abrir SUNAT <ExternalLink size={14} className="ml-1" />
                    </a>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'ciiu' && (
          <div>
            <div className="mb-4">
              <h4 className="text-sm font-bold text-gray-800 uppercase m-0">Clasificación CIIU Rev. 4</h4>
            </div>

            {ciiuVal?.response_payload?.results && ciiuVal.response_payload.results.length > 0 ? (
              <div className="val-table-container">
                <table className="val-table">
                  <thead>
                    <tr>
                      <th style={{ width: '40px', textAlign: 'center' }}>#</th>
                      <th style={{ width: '100px' }}>Tipo</th>
                      <th style={{ width: '80px' }}>CIIU</th>
                      <th>Denominación INEI</th>
                      <th style={{ width: '120px' }}>Estado</th>
                      <th style={{ width: '100px' }}>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ciiuVal.response_payload.results.map((act: any, idx: number) => (
                      <tr key={idx}>
                        <td style={{ textAlign: 'center' }}>{idx + 1}</td>
                        <td><span className="val-badge val-secondary">{act.tipo}</span></td>
                        <td style={{ fontFamily: 'monospace' }}>{act.codigo_ciiu || '-'}</td>
                        <td style={{ fontWeight: 500 }}>{act.descripcion_inei || act.actividad_sunat}</td>
                        <td>
                          {act.status === 'PASSED' ? <span className="val-badge val-success">CIIU verificado</span> : <span className="val-badge val-warning">Revisión</span>}
                        </td>
                        <td>
                          {act.codigo_ciiu && (
                            <button
                              onClick={() => onCiiuDetail(act)}
                              style={{ color: '#2563eb', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                            >
                              Ver detalle
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-500 italic">No se encontró clasificación CIIU.</p>
            )}
          </div>
        )}

        {activeTab === 'rnp_fup' && (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="border border-gray-200 rounded p-5 bg-white shadow-sm">
              <h4 className="text-sm font-bold text-gray-800 uppercase mb-4 border-b pb-2">RNP - Registro Nacional de Proveedores</h4>
              {rnpVal?.response_payload?.registro ? (
                <>
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div><span className="text-xs font-bold text-gray-500 uppercase">Registro</span><p className="m-0 text-sm font-medium">{rnpVal.response_payload.registro}</p></div>
                    <div className="col-span-2 grid grid-cols-2">
                      <div><span className="text-xs font-bold text-gray-500 uppercase">Bienes</span><p className="m-0 text-sm">{rnpVal.response_payload.bienes ? 'Sí' : 'No'}</p></div>
                      <div><span className="text-xs font-bold text-gray-500 uppercase">Servicios</span><p className="m-0 text-sm">{rnpVal.response_payload.servicios ? 'Sí' : 'No'}</p></div>
                    </div>
                  </div>
                  <a href={`https://www.rnp.gob.pe/Constancia/RNP_Constancia/default_Todos.asp?RUC=${supplier.ruc}`} target="_blank" rel="noopener noreferrer" className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-1.5 rounded inline-flex items-center no-underline font-medium border border-gray-300">
                    Abrir constancia oficial <ExternalLink size={14} className="ml-1" />
                  </a>
                </>
              ) : (
                <div className="flex flex-col items-start">
                  <Badge variant="warning" className="mb-3">No disponible</Badge>
                  <a href={`https://www.rnp.gob.pe/Constancia/RNP_Constancia/default_Todos.asp?RUC=${supplier.ruc}`} target="_blank" rel="noopener noreferrer" className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-1.5 rounded inline-flex items-center no-underline font-medium border border-gray-300">
                    Buscar constancia oficial <ExternalLink size={14} className="ml-1" />
                  </a>
                </div>
              )}
            </div>

            <div className="border border-gray-200 rounded p-5 bg-white shadow-sm">
              <h4 className="text-sm font-bold text-gray-800 uppercase mb-4 border-b pb-2">FUP - Ficha Única del Proveedor</h4>
              {fupVal?.status === 'PASSED' ? (
                <>
                  <div className="mb-4">
                    <span className="text-xs font-bold text-gray-500 uppercase">Estado extracción</span>
                    <p className="m-0 text-sm font-medium text-green-600">Disponible</p>
                  </div>
                  <a href={`https://apps.osce.gob.pe/perfilprov-ui/ficha/${supplier.ruc}`} target="_blank" rel="noopener noreferrer" className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-1.5 rounded inline-flex items-center no-underline font-medium border border-gray-300">
                    Abrir FUP oficial <ExternalLink size={14} className="ml-1" />
                  </a>
                </>
              ) : (
                <div className="flex flex-col items-start">
                  <Badge variant="warning" className="mb-3">No disponible / Fallo extracción</Badge>
                  <a href={`https://apps.osce.gob.pe/perfilprov-ui/ficha/${supplier.ruc}`} target="_blank" rel="noopener noreferrer" className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-1.5 rounded inline-flex items-center no-underline font-medium border border-gray-300">
                    Abrir FUP oficial <ExternalLink size={14} className="ml-1" />
                  </a>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'manuales' && (
          <div>
            <h4 className="text-sm font-bold text-gray-800 uppercase mb-4 m-0">Validaciones Manuales</h4>
            {manualValidations.length > 0 ? (
              <div className="overflow-x-auto rounded border border-gray-200">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Fecha</th>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Fuente</th>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Resultado</th>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Verificado por</th>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Observación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {manualValidations.sort((a, b) => new Date(b.requested_at).getTime() - new Date(a.requested_at).getTime()).map((v) => (
                      <tr key={v.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm text-gray-600">{new Date(v.requested_at).toLocaleString()}</td>
                        <td className="px-4 py-3 text-sm font-medium">{v.source}</td>
                        <td className="px-4 py-3 text-sm">
                          <Badge variant={v.manual_result === 'VALIDATED' ? 'success' : v.manual_result === 'REJECTED' ? 'danger' : 'warning'}>
                            {v.manual_result}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600">
                          {v.verified_by_user?.full_name || v.verified_by_user?.username || `ID ${v.verified_by_user_id}`}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-800 truncate max-w-[200px]" title={v.manual_observation}>
                          {v.manual_observation}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-500 italic">No hay validaciones manuales registradas.</p>
            )}
          </div>
        )}

        {activeTab === 'historial' && (
          <div>
            <h4 className="text-sm font-bold text-gray-800 uppercase mb-4 m-0">Historial Técnico</h4>
            {validations.length > 0 ? (
              <div className="overflow-x-auto rounded border border-gray-200">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Fecha</th>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Fuente</th>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Tipo</th>
                      <th className="px-4 py-2 text-xs font-bold text-gray-500 uppercase border-b border-gray-200">Resultado Técnico</th>
                    </tr>
                  </thead>
                  <tbody>
                    {validations.sort((a, b) => new Date(b.requested_at).getTime() - new Date(a.requested_at).getTime()).slice(0, 10).map((v) => (
                      <tr key={v.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm text-gray-600">{new Date(v.requested_at).toLocaleString()}</td>
                        <td className="px-4 py-3 text-sm font-medium">{v.source}</td>
                        <td className="px-4 py-3 text-sm">
                          {v.validation_mode === 'MANUAL' ? <Badge variant="primary" className="text-[10px]">MANUAL</Badge> : <Badge variant="secondary" className="text-[10px]">API</Badge>}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <ValidationStatusBadge status={v.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {validations.length > 10 && (
                  <div className="px-4 py-3 text-center bg-gray-50 border-t border-gray-200">
                    <span className="text-xs text-gray-500 italic">+ {validations.length - 10} registros más antiguos no mostrados.</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-gray-500 italic">No hay historial.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
