import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';

const SettingsPage: React.FC = () => {
  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Configuración</h1>
        <p className="text-gray-600">Gestione la configuración del sistema</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Configuración Institucional</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="border-dashed border-2 border-gray-300 rounded p-12 text-center text-gray-500">
            [Placeholder para Logo Institucional y Configuración]
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default SettingsPage;
