import React, { useState, useRef, useEffect } from 'react';
import { Send, ImagePlus, X, Paperclip } from 'lucide-react';

interface InputBarProps {
  onSend: (prompt: string, files: { product?: File; reference?: File; logo?: File }) => void;
  disabled?: boolean;
}

const InputBar: React.FC<InputBarProps> = ({ onSend, disabled }) => {
  const [prompt, setPrompt] = useState('');
  const [files, setFiles] = useState<{ product?: File; reference?: File; logo?: File }>({});
  
  const productInputRef = useRef<HTMLInputElement>(null);
  const referenceInputRef = useRef<HTMLInputElement>(null);
  const logoInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      // Set a max height (e.g., 128px) and let it scroll if it exceeds that
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(scrollHeight, 128)}px`;
    }
  }, [prompt]);

  const handleFileChange = (type: 'product' | 'reference' | 'logo', e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setFiles(prev => ({ ...prev, [type]: file }));
    }
    // Clear input so same file can be selected again
    e.target.value = '';
  };

  const removeFile = (type: 'product' | 'reference' | 'logo') => {
    setFiles(prev => {
      const newFiles = { ...prev };
      delete newFiles[type];
      return newFiles;
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (prompt.trim() || Object.keys(files).length > 0) {
      onSend(prompt, files);
      setPrompt('');
      setFiles({});
      // Reset textarea height after submit
      if (textareaRef.current) {
         textareaRef.current.style.height = 'auto';
      }
    }
  };

  return (
    <div className="border-t border-gray-800 bg-gray-900 p-4 pb-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-wrap gap-2 mb-3">
          {files.product && (
            <FileBadge label="Product" file={files.product} onRemove={() => removeFile('product')} />
          )}
          {files.reference && (
            <FileBadge label="Ref" file={files.reference} onRemove={() => removeFile('reference')} />
          )}
          {files.logo && (
            <FileBadge label="Logo" file={files.logo} onRemove={() => removeFile('logo')} />
          )}
        </div>

        <form onSubmit={handleSubmit} className="relative flex items-end gap-2 bg-gray-800 rounded-2xl p-2 pl-4 border border-gray-700 shadow-xl">
          <div className="flex gap-1 mb-1">
            <button
              type="button"
              onClick={() => productInputRef.current?.click()}
              className={`p-2 rounded-lg hover:bg-gray-700 transition-colors ${files.product ? 'text-blue-400' : 'text-gray-400'}`}
              title="Add Product Image (Type A)"
            >
              <ImagePlus size={20} />
            </button>
            <button
              type="button"
              onClick={() => referenceInputRef.current?.click()}
              className={`p-2 rounded-lg hover:bg-gray-700 transition-colors ${files.reference ? 'text-purple-400' : 'text-gray-400'}`}
              title="Add Reference Ad (Type B)"
            >
              <Paperclip size={20} />
            </button>
          </div>

          <textarea
            ref={textareaRef}
            rows={1}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder="Describe the ad creative you want..."
            className="flex-1 bg-transparent border-none focus:ring-0 text-gray-100 placeholder-gray-500 py-2 max-h-32 resize-none overflow-y-auto"
            disabled={disabled}
            style={{ minHeight: '40px' }}
          />

          <button
            type="submit"
            disabled={disabled || (!prompt.trim() && Object.keys(files).length === 0)}
            className="p-2 mb-1 bg-blue-600 text-white rounded-xl hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors shrink-0"
          >
            <Send size={20} />
          </button>

          <input type="file" ref={productInputRef} className="hidden" accept="image/*" onChange={(e) => handleFileChange('product', e)} />
          <input type="file" ref={referenceInputRef} className="hidden" accept="image/*" onChange={(e) => handleFileChange('reference', e)} />
          <input type="file" ref={logoInputRef} className="hidden" accept="image/*" onChange={(e) => handleFileChange('logo', e)} />
        </form>
        
        <p className="text-center text-[10px] text-gray-500 mt-2">
          OpenAI Pipeline: Generates copy + images based on your source assets.
        </p>
      </div>
    </div>
  );
};

const FileBadge = ({ label, file, onRemove }: { label: string, file: File, onRemove: () => void }) => {
  return (
    <div className="flex items-center gap-1 bg-gray-800 border border-gray-700 rounded-full px-2 py-1 text-xs text-gray-300">
      <span className="font-semibold text-blue-400">{label}:</span>
      <span className="truncate max-w-[100px]">{file.name}</span>
      <button onClick={onRemove} className="hover:text-red-400">
        <X size={14} />
      </button>
    </div>
  );
};

export default InputBar;
