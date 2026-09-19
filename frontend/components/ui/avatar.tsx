import * as React from "react";

export function Avatar({ className = "", children }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200 ${className}`}>{children}</div>;
}

export function AvatarImage(props: React.ImgHTMLAttributes<HTMLImageElement>) {
  return <img {...props} />;
}

export function AvatarFallback({ className = "", ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={className} {...props} />;
}
