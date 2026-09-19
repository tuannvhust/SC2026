import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Circle } from 'lucide-react';

export function ChatHeader() {
  return (
    <header className="flex items-center justify-between border-b pb-2 mb-4">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
        SUDOTECH
      </h1>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="flex items-center gap-1">
          <Circle className="h-2 w-2 fill-emerald-500 text-emerald-500" />
          Online
        </Badge>
        <Badge variant="secondary">Gemini + Groq</Badge>
      </div>
    </header>
  );
}
