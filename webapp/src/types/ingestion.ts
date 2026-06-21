export type Ecosystem = 'npm' | 'pypi' | 'cargo' | 'go' | 'maven' | 'rubygems';
export type Tier = 'popular' | 'niche';

export interface FunctionIn {
  qualified_name: string;
  kind?: string;
  signature?: string;
  summary?: string;
  description?: string;
  params?: Record<string, unknown> | unknown[] | null;
  returns?: string;
  source_url?: string;
}

export interface LibraryIngestRequest {
  ecosystem: Ecosystem;
  name: string;
  version?: string;
  summary?: string;
  homepage?: string;
  docs_url?: string;
  tier: Tier;
  tags: string[];
  functions: FunctionIn[];
}

export interface LibraryIngestResponse {
  library_id: string;
  function_table: string;
  functions_upserted: number;
  tags_upserted: number;
}
