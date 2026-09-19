import * as React from "react";

export function Badge({ className = "", variant = "secondary", ...props }: React.HTMLAttributes<HTMLSpanElement> & { variant?: "secondary" | "outline" }) {
  const variantClass = variant === "outline" ? "border border-slate-300 bg-transparent dark:border-slate-700" : "bg-slate-100 dark:bg-slate-800";
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium text-slate-700 dark:text-slate-200 ${variantClass} ${className}`} {...props} />;
}
