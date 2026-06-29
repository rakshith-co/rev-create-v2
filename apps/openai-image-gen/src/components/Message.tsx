import React from 'react';
import { User, Bot, Loader2 } from 'lucide-react';

export interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  images?: string[];
  status?: 'sending' | 'polling' | 'success' | 'failed';
}

const Message: React.FC<MessageProps> = ({ role, content, images, status }) => {
  const isUser = role === 'user';

  return (
    <div className={`flex w-full mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center ${isUser ? 'bg-blue-600 ml-3' : 'bg-gray-700 mr-3'}`}>
          {isUser ? <User size={20} className="text-white" /> : <Bot size={20} className="text-white" />}
        </div>
        
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          <div className={`px-4 py-3 rounded-2xl ${isUser ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-gray-800 text-gray-100 rounded-tl-none'}`}>
            <p className="whitespace-pre-wrap">{content}</p>
          </div>

          {status === 'polling' && !images && (
            <div className="mt-3 flex items-center text-gray-400 text-sm">
              <Loader2 className="animate-spin mr-2" size={16} />
              Generating images...
            </div>
          )}

          {images && images.length > 0 && (
            <div className="mt-4 grid grid-cols-2 gap-2 w-full max-w-md">
              {images.map((img, idx) => (
                <div key={idx} className="relative aspect-square rounded-lg overflow-hidden border border-gray-700 group">
                  <img src={img} alt={`Generated ${idx}`} className="w-full h-full object-cover" />
                  <a 
                    href={img} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity text-white text-xs font-medium"
                  >
                    View Full
                  </a>
                </div>
              ))}
            </div>
          )}
          
          {status === 'failed' && (
            <div className="mt-2 text-red-400 text-sm italic">
              Failed to generate images.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Message;
