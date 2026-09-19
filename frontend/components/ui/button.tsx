import * as React from "react";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "outline" | "ghost";
  size?: "default" | "icon";
};

export function Button({
  className = "",
  variant = "default",
  size = "default",
  ...props
}: ButtonProps) {
  const styles = {
    default: "bg-blue-600 text-white hover:bg-blue-700",
    outline: "border border-slate-200 bg-transparent hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800",
    ghost: "hover:bg-slate-100 dark:hover:bg-slate-800",
  };
  return (
    <button
      className={`inline-flex items-center justify-center rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${size === "icon" ? "h-9 w-9" : "px-3 py-2 text-sm"} ${className}`}
      {...props}
    />
  );
}
