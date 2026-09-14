import React from 'react';
import {
  Home,
  FileText,
  FolderOpen,
  Users,
  ClipboardList,
  ShieldCheck,
  BarChart3,
  Trophy,
  Flag,
  Sparkles,
  Clock3
} from 'lucide-react';

interface CaseWorkspaceNavProps {
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

const workspaceModules = [
  { id: 'resumen', label: 'Resumen', icon: Home },
  { id: 'requerimiento', label: 'Requerimiento', icon: FileText },
  { id: 'documentos', label: 'Documentos', icon: FolderOpen },
  { id: 'proveedores', label: 'Proveedores', icon: Users },
  { id: 'ofertas', label: 'Ofertas', icon: ClipboardList },
  { id: 'validaciones', label: 'Validaciones', icon: ShieldCheck },
  { id: 'evaluacion', label: 'Evaluación', icon: BarChart3 },
  { id: 'seleccion', label: 'Selección', icon: Trophy },
  { id: 'resultado', label: 'Resultado', icon: Flag },
  { id: 'ia', label: 'Asistente IA', icon: Sparkles },
  { id: 'historial', label: 'Historial', icon: Clock3 },
];

export const CaseWorkspaceNav: React.FC<CaseWorkspaceNavProps> = ({ activeTab, onTabChange }) => {
  return (
    <div className="case-workspace-nav">
      <div className="case-workspace-nav__scroll">
        {workspaceModules.map((module) => {
          const Icon = module.icon;
          const isActive = activeTab === module.id;

          return (
            <button
              key={module.id}
              onClick={() => onTabChange(module.id)}
              className={`case-workspace-nav__item ${isActive ? 'case-workspace-nav__item--active' : ''}`}
            >
              <Icon size={22} className="case-workspace-nav__icon" />
              <span className="case-workspace-nav__label">
                {module.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
