export type Message = {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
};

export type Thread = {
  id: string;
  title: string;
  messages: Message[];
  updatedAt?: string;
};

export type DocumentMeta = {
  filename?: string;
  chunks?: number;
  documents?: number;
  size?: number;
  uploadedAt?: string;
};

export type AgentRole = "auto" | "research" | "code" | "data" | "docs";

export type AgentSkill = {
  id: string;
  name: string;
  category: "research" | "code" | "data" | "analysis" | "automation";
  description: string;
  prompt: string;
  icon: string;
  agentRole: AgentRole;
  badge?: string;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: string;
};

export type StoredDocument = {
  id: string;
  doc_id?: string;
  filename: string;
  size_bytes: number;
  mime_type?: string;
  drive_file_id?: string;
  drive_web_link?: string;
  drive_folder_id?: string;
  chunks_count?: number;
  chunks?: number;
  status: string;
  created_at?: string;
};

