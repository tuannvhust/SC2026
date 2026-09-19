import * as React from "react";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className = "", ...props }, ref) => (
    <textarea ref={ref} className={`rounded-lg border border-slate-200 bg-white px-3 py-2 outline-none transition focus:border-blue-500 dark:border-slate-700 dark:bg-slate-900 ${className}`} {...props} />
  ),
);
Textarea.displayName = "Textarea";
