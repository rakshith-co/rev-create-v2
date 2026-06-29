import { useState } from 'react';
import { sendChatMessage } from '../services/api';
import type { ChatMessage } from '../services/api';
import type { MessageProps } from '../components/Message';

export const useChat = () => {
  const [messages, setMessages] = useState<MessageProps[]>([]);
  const [isSending, setIsSending] = useState(false);

  const sendMessage = async (prompt: string, files: { product?: File; reference?: File; logo?: File }) => {
    setIsSending(true);
    
    // For this iteration, we pass the prompt directly.
    let fullPrompt = prompt || 'Generate an ad creative';
    if (files.product || files.reference || files.logo) {
      fullPrompt += '\n\n[Attached files: ';
      if (files.product) fullPrompt += `Product=${files.product.name} `;
      if (files.reference) fullPrompt += `Reference=${files.reference.name} `;
      if (files.logo) fullPrompt += `Logo=${files.logo.name} `;
      fullPrompt += ']';
    }
    
    const userMsg: MessageProps = {
      role: 'user',
      content: fullPrompt,
    };
    
    setMessages(prev => [...prev, userMsg]);

    const assistantMsgIndex = messages.length + 1;
    const assistantMsg: MessageProps = {
      role: 'assistant',
      content: 'Generating image...',
      status: 'polling',
    };
    
    setMessages(prev => [...prev, assistantMsg]);

    try {
      // Build history to send
      const historyToSend: ChatMessage[] = messages.map(m => ({
        role: m.role,
        content: m.content,
      }));
      historyToSend.push({ role: 'user', content: fullPrompt });

      const response = await sendChatMessage(historyToSend);
      
      setMessages(prev => {
        const next = [...prev];
        next[assistantMsgIndex] = {
          ...next[assistantMsgIndex],
          content: response.content || 'Here is your generated image.', // Provide fallback text if empty
          images: response.images,
          status: 'success',
        };
        return next;
      });
      
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => {
        const next = [...prev];
        next[assistantMsgIndex] = {
          ...next[assistantMsgIndex],
          content: 'Error: Failed to generate the image.',
          status: 'failed',
        };
        return next;
      });
    } finally {
      setIsSending(false);
    }
  };

  return {
    messages,
    sendMessage,
    isSending,
  };
};
