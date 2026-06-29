import ChatWindow from './components/ChatWindow';
import InputBar from './components/InputBar';
import { useChat } from './hooks/useChat';
import { Sparkles } from 'lucide-react';

function App() {
  const { messages, sendMessage, isSending } = useChat();

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 bg-gray-900 border-b border-gray-800 shrink-0 shadow-md">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-blue-600 rounded-lg">
            <Sparkles size={20} className="text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">revCreate <span className="text-blue-500">OpenAI</span></h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="px-3 py-1 bg-gray-800 rounded-full text-xs font-medium text-gray-400 border border-gray-700">
            Pipeline: v2 (OpenAI Image-2)
          </div>
        </div>
      </header>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col min-h-0">
        <ChatWindow messages={messages} />
        <InputBar onSend={sendMessage} disabled={isSending} />
      </main>
    </div>
  );
}

export default App;
