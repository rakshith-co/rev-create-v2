import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const API_KEY = import.meta.env.VITE_API_KEY || 'rev-create-dev-key';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'X-API-Key': API_KEY,
  },
});

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  image?: string; // New direct image property
}

export const sendChatMessage = async (messages: ChatMessage[]) => {
  // Call the new generic OpenAI v2 endpoint
  const response = await api.post('/v2/openai/chat', { messages });
  const choice = response.data.choices[0];
  
  return {
    role: choice.message.role as 'assistant',
    content: choice.message.content,
    images: choice.message.image ? [choice.message.image] : []
  };
};

// Keeping the old interfaces around just in case
export interface JobStatus {
  id: string;
  status: 'pending' | 'generating_copy' | 'processing' | 'done' | 'failed' | 'partial_failure';
  creatives: {
    id: string;
    url: string;
    status: string;
  }[];
  headline?: string;
  body_copy?: string;
  image_prompt?: string;
}
