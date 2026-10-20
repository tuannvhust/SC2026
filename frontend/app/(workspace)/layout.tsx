"use client";

import { WorkspaceProvider } from "@/components/workspace-provider";
import { Sidebar } from "@/components/sidebar";
import { Topbar, Overlays } from "@/components/chrome";
import { useState } from "react";

export default function WorkspaceLayout({
	children,
}: Readonly<{ children: React.ReactNode }>) {
	const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
	return (
		<WorkspaceProvider>
			<div className={`grid min-h-screen grid-cols-1 transition-[grid-template-columns] duration-200 ${sidebarCollapsed ? "lg:grid-cols-[72px_minmax(0,1fr)]" : "lg:grid-cols-[224px_minmax(0,1fr)]"}`}>
				<Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((collapsed) => !collapsed)} />
				<main className="min-w-0">
					<Topbar />
					<div className="mx-auto max-w-[1700px] px-4 py-4 sm:px-7 sm:py-6">
						{children}
					</div>
				</main>
			</div>
			<Overlays />
		</WorkspaceProvider>
	);
}
