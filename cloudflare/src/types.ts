export interface Env {
  DB: D1Database;
  ASSETS?: Fetcher;
  NVIDIA_API_KEY?: string;
  JWT_SECRET?: string;
  GOOGLE_CLIENT_ID?: string;
}

export interface UserContext {
  userId: string;
  userRole: string;
  userEmail: string;
}

export interface UserRow {
  id: string;
  email: string;
  hashed_password: string;
  salt: string;
  full_name: string | null;
  avatar_url: string | null;
  role: string;
  provider: string;
  created_at: string;
  updated_at: string;
}

export interface StoredDocument {
  id: string;
  user_id: string;
  filename: string;
  mime_type?: string;
  size_bytes: number;
  r2_key?: string | null;
  text_content?: string | null;
  chunks_count: number;
  chunks?: number;
  status: string;
  created_at?: string;
}

export interface ThreadRow {
  id: string;
  user_id: string;
  title: string;
  active_document_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageRow {
  id: string;
  thread_id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls: string | null;
  tools_used: string | null;
  created_at: string;
}
