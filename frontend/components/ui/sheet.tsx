"use client";

import * as React from "react";

const SheetContext = React.createContext<{ close: () => void } | null>(null);

export function Sheet({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <SheetContext.Provider value={{ close: () => setOpen(false) }}>
      <div className="contents">
        {React.Children.map(children, (child) =>
          React.isValidElement(child) ? React.cloneElement(child, { open, setOpen } as never) : child,
        )}
      </div>
    </SheetContext.Provider>
  );
}

export function SheetTrigger({ children, asChild }: { children: React.ReactElement; asChild?: boolean }) {
  return React.cloneElement(children, { onClick: () => (children.props as { onClick?: () => void }).onClick?.() } as never);
}

export function SheetContent({ children, side = "left", className = "" }: { children: React.ReactNode; side?: "left" | "right"; className?: string }) {
  return <div className={`fixed inset-y-0 z-50 ${side === "left" ? "left-0" : "right-0"} w-72 border-r border-slate-200 bg-white p-4 shadow-xl dark:border-slate-800 dark:bg-slate-950 ${className}`}>{children}</div>;
}
