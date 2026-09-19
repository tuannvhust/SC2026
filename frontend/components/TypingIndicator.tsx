import React from 'react';

export function TypingIndicator() {
  return (
    <div className="flex items-center space-x-1">
      <span className="inline-block w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:0ms]"></span>
      <span className="inline-block w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:150ms]"></span>
      <span className="inline-block w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:300ms]"></span>
    </div>
  );
}
