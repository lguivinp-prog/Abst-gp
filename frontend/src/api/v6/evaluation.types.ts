export interface EvaluationResponse {
  id: number;
  supplier_offer_id: number;
  requirement_id: number;
  status: string;
  explanation?: string;
  evaluation_confidence?: number;
}

export interface EvaluationUpdate {
  status: string;
  explanation: string;
}
