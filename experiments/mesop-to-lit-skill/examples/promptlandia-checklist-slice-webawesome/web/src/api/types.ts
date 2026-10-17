// Typed mirror of the backend api/schemas.py §3.3 shapes. The frontend receives
// a normal typed JSON body (no Mesop JSON-in-state hack).

export interface ChecklistItem {
  issue_name: string;
  location_in_prompt: string;
  rationale: string;
  impact_analysis: string;
  severity: string;
  solution: string;
}

export interface ChecklistCategory {
  name: string;
  has_issue: boolean;
  explanation: string;
  items: ChecklistItem[];
}

export interface ChecklistResponse {
  categories: ChecklistCategory[];
  raw: string | null;
}

export interface ApiError {
  code: string;
  message: string;
}
