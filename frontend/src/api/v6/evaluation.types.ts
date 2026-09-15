export interface EvaluationResponse {
  id: number;
  supplier_offer_id: number;
  requirement_id: number;
  status: string;
  explanation?: string;
  evaluation_confidence?: number;
  requirement_description?: string;
  requirement_type?: string;
}

export interface EvaluationUpdate {
  status: string;
  explanation: string;
}
