import React, { useState } from 'react';
import { Upload } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { casesService } from '../../../api/cases.service';
import { AppError } from '../../../api/apiError';
import { MAX_REQUIREMENT_SIZE_MB } from '../../../config/documentLimits';

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

    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > MAX_REQUIREMENT_SIZE_MB) {
      setErrorMsg(`El archivo excede el tamaño máximo permitido de ${MAX_REQUIREMENT_SIZE_MB}MB.`);
      return;
    }

    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await casesService.uploadRequirement(caseId, file);
      if (res && res.job_id) {
        onUploadSuccess(res.job_id);
      } else {
        throw new Error('Respuesta del servidor sin job_id');
      }
    } catch (error: any) {
      if (error instanceof AppError) {
        setErrorMsg(error.message);
      } else {
        setErrorMsg('Error al subir requerimiento');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-container p-4 border rounded-md bg-white shadow-sm">
      <h3 className="text-lg font-medium mb-2 text-gray-800">1. Subir Requerimiento</h3>
      <p className="text-sm text-gray-600 mb-4">Seleccione el PDF con el requerimiento (TDR/EETT).</p>
      
      {errorMsg && (
        <div className="text-red-700 mb-4 text-sm bg-red-50 border border-red-100 p-3 rounded-md">
          {errorMsg}
        </div>
      )}
      
      <input 
        type="file" 
        data-testid="upload-requirement"
        accept="application/pdf" 
        onChange={(e) => setFile(e.target.files?.[0] || null)} 
        className="mb-4 block w-full text-sm text-gray-500
          file:mr-4 file:py-2 file:px-4
          file:rounded-md file:border-0
          file:text-sm file:font-semibold
          file:bg-blue-50 file:text-blue-700
          hover:file:bg-blue-100"
        disabled={loading}
      />
      
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
