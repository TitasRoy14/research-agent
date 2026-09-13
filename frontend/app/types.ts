export interface Claim {
  text: string;
  source_ids: string[];
}

export interface ResearchAnswer {
  summary: string;
  claims: Claim[];
  conflicts: string[];
  uncertainties: string[];
}

export interface SourceRef {
  id: string;
  url: string;
  title: string;
  providers: string[];
  relevance_score: number | null;
  content_fetched: boolean;
}

export interface ResearchResponse {
  question: string;
  sub_queries: string[];
  answer: ResearchAnswer;
  sources: SourceRef[];
  provider_errors: string[];
}
