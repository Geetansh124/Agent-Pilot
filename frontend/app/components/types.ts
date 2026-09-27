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
