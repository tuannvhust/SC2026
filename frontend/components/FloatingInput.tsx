import React, { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send } from 'lucide-react';
import { PROMPT_CHIPS } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

interface FloatingInputProps {
  onSend: (text: string) => void;
  loading: boolean;
}

export function FloatingInput({ onSend, loading }: FloatingInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto‑grow textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  const handleSend = () => {
    if (!input.trim()) return;
    onSend(input);
    setInput('');
  };

  const handleChipClick = (chip: string) => {
    setInput(chip);
    onSend(chip);
    setInput('');
  };

  return (
    <div className="fixed inset-x-0 bottom-0 mb-4 mx-auto max-w-2xl w-full px-4">
      {/* Prompt chips */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {PROMPT_CHIPS.map((chip) => (
          <Badge
            key={chip}
            variant="secondary"
            className="cursor-pointer whitespace-nowrap hover:bg-blue-100 dark:hover:bg-slate-700"
            onClick={() => handleChipClick(chip)}
          >
            {chip}
          </Badge>
        ))}
      </div>
      <div className="flex items-end gap-2 rounded-2xl bg-background/95 backdrop-blur-sm p-3 shadow-lg">
        <Textarea
          ref={textareaRef}
          placeholder="Nhập tin nhắn…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={1}
          disabled={loading}
          className="flex-1 resize-none border-none focus:ring-0"
        />
        <Button
          variant="default"
          size="icon"
          className={input.trim() ? "bg-emerald-600 hover:bg-emerald-700" : "bg-slate-300 text-slate-500 hover:bg-slate-300 dark:bg-zinc-700 dark:text-zinc-400"}
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          <Send className="h-5 w-5" />
        </Button>
      </div>
    </div>
  );
}
