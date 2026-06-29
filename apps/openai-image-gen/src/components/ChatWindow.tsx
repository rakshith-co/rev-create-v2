import React, { useRef, useEffect } from 'react';
import Message from './Message';
import type { MessageProps } from './Message';

interface ChatWindowProps {
  messages: MessageProps[];
}

const ChatWindow: React.FC<ChatWindowProps> = ({ messages }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div 
      ref={scrollRef}
      className="flex-1 overflow-y-auto p-4 md:p-8 space-y-2 scroll-smooth"
    >
      <div className="max-w-4xl mx-auto w-full">
        {messages.length === 0 ? (
          <div className="h-[60vh] flex flex-col items-center justify-center text-center">
            <div className="w-16 h-16 bg-gray-800 rounded-2xl flex items-center justify-center mb-4 border border-gray-700 shadow-lg">
              <span className="text-3xl">✨</span>
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">OpenAI Image Gen</h2>
            <p className="text-gray-400 max-w-sm">
              Upload your product images and reference ads to generate custom creative variations using the OpenAI pipeline.
            </p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <Message key={idx} {...msg} />
          ))
        )}
      </div>
    </div>
  );
};

export default ChatWindow;
