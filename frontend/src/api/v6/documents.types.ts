export interface DocumentResponse {
  id: number;
  case_id: number;
  original_filename: string;
  processing_status?: string | null;
  created_at?: string | null;
  document_type?: string | null;
  extraction_ready: boolean;
}
