import React, { useState } from 'react';
import { Upload } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import apiClient from '../../../api/client';

interface QuotationUploadProps {
  caseId: string;
  onUploadSuccess: () => void;
  disabled: boolean;
}

export const QuotationUpload: React.FC<QuotationUploadProps> = ({ caseId, onUploadSuccess, disabled }) => {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setErrorMsg(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      await apiClient.postForm(`/cases/${caseId}/quotation/upload`, formData);
      onUploadSuccess();
    } catch (error: any) {
      console.error('Error uploading quotation:', error);
      let errorText = 'Error al subir cotización';
      if (error.response?.data?.detail) {
        if (typeof error.response.data.detail === 'string') {
          errorText = error.response.data.detail;
        } else if (Array.isArray(error.response.data.detail)) {
          errorText = error.response.data.detail.map((e: any) => e.msg).join(', ');
        } else {
          errorText = JSON.stringify(error.response.data.detail);
        }
      } else if (error.message) {
        errorText = error.message;
      }
      setErrorMsg(errorText);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className={disabled ? 'opacity-50' : ''}>
      <CardHeader>
        <CardTitle>2. Cotización</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm mb-4">Suba la cotización del proveedor para extraer condiciones.</p>
        {errorMsg && <div className="text-red-600 mb-4 text-sm bg-red-50 p-2 rounded">{errorMsg}</div>}
        <input 
          type="file" 
          accept="application/pdf" 
          onChange={(e) => setFile(e.target.files?.[0] || null)} 
          className="mb-4 block" 
          disabled={disabled || loading}
        />
        <Button 
          leftIcon={<Upload size={18} />} 
          onClick={handleUpload} 
          disabled={!file || disabled || loading}
        >
          {loading ? 'Procesando...' : 'Subir Cotización'}
        </Button>
      </CardContent>
    </Card>
  );
};
