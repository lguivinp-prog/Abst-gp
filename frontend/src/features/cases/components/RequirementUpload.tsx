import React, { useState } from 'react';
import { Upload } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import apiClient from '../../../api/client';

interface RequirementUploadProps {
  caseId: string;
  onUploadSuccess: (jobId: string) => void;
}

export const RequirementUpload: React.FC<RequirementUploadProps> = ({ caseId, onUploadSuccess }) => {
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
      const res = await apiClient.postForm(`/cases/${caseId}/requirement/upload`, formData);
      if (res.data && res.data.job_id) {
        onUploadSuccess(res.data.job_id);
      } else {
        throw new Error('Respuesta del servidor sin job_id');
      }
    } catch (error: any) {
      console.error('Error uploading requirement:', error);
      let errorText = 'Error al subir requerimiento';
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
    <div className="upload-container p-4 border rounded-md bg-white">
      <h3 className="text-lg font-medium mb-2">1. Subir Requerimiento</h3>
      <p className="text-sm text-gray-600 mb-4">Seleccione el PDF con el requerimiento (TDR/EETT).</p>
      {errorMsg && <div className="text-red-600 mb-4 text-sm bg-red-50 p-2 rounded">{errorMsg}</div>}
      <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} className="mb-4 block" />
      <Button 
        leftIcon={<Upload size={18} />} 
        onClick={handleUpload} 
        disabled={!file || loading}
      >
        {loading ? 'Subiendo...' : 'Subir PDF'}
      </Button>
    </div>
  );
};
