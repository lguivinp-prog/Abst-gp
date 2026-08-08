export type JobStatus = 
  | 'IDLE'
  | 'QUEUED' 
  | 'PROCESSING' 
  | 'READY' 
  | 'FAILED' 
  | 'finished' 
  | 'failed' 
  | 'started' 
  | 'deferred' 
  | 'queued';

export interface ProcessingJobResponse {
  job_id: string;
  case_id?: number | null;
  document_id?: number | null;
  job_type?: string;
  worker_type?: string;
  status: string;
  progress: number;
  message: string;
  case_status?: string | null;
  result_summary?: Record<string, any> | null;
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  already_completed?: boolean;
}

export interface QuotationUploadResponse {
  message: string;
  job_id?: string;
  status?: string;
}

export interface ComparisonRunResponse {
  message: string;
  job_id?: string;
  status?: string;
  alreadyCompleted?: boolean;
  already_completed?: boolean;
}
