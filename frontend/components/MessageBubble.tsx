import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, Copy, Check, ThumbsUp, ThumbsDown, RotateCcw } from 'lucide-react';
import { copyToClipboard } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { useState } from 'react';

interface Message {
  role: 'user' | 'assistant';
  text: string;
}

export function MessageBubble({
  msg,
  onCopy,
  onRefresh,
}: {
  msg: Message;
  onCopy: () => void;
  onRefresh: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await copyToClipboard(msg.text);
    setCopied(true);
    onCopy();
    setTimeout(() => setCopied(false), 2000);
  };

  const BotAvatar = (
    <Avatar className="h-8 w-8 mr-2">
      <AvatarFallback>
        <Bot className="h-4 w-4" />
      </AvatarFallback>
    </Avatar>
  );

  return (
    <div className={`mb-5 flex items-end gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      {msg.role === 'assistant' && BotAvatar}
      <div
        className={`max-w-[85%] break-words px-4 py-3 text-sm leading-6 shadow-sm md:max-w-[75%] ${
          msg.role === 'user'
            ? 'rounded-2xl rounded-tr-none bg-blue-600 text-white'
            : 'rounded-2xl rounded-tl-none bg-slate-100 text-slate-800 dark:bg-zinc-800 dark:text-zinc-100'
        }`}
      >
        {msg.role === 'assistant' ? (
          <div className="max-w-none [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:whitespace-pre-line [&_p]:my-1 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
          </div>
        ) : (
          msg.text
        )}
      </div>
      {msg.role === 'assistant' && (
        <div className="flex items-center ml-2 space-x-1">
          <Button variant="ghost" size="icon" aria-label="Thích" onClick={() => undefined}>
            <ThumbsUp className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Không thích" onClick={() => undefined}>
            <ThumbsDown className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={handleCopy}>
            {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" aria-label="Gửi lại" onClick={onRefresh}>
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
