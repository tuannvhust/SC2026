"use client";

import { WorkspaceProvider, useWorkspace } from "@/components/workspace-provider";
import { Sidebar } from "@/components/sidebar";
import { Topbar, Overlays } from "@/components/chrome";
import { WorkspaceView } from "@/components/view-workspace";
import { CustomersView } from "@/components/view-customers";
import { ProductsView } from "@/components/view-products";
import { PromotionsView } from "@/components/view-promotions";
import { PoliciesView } from "@/components/view-policies";
import { EvaluationView, ImprovementView } from "@/components/view-eval";

function Router() {
  const { view } = useWorkspace();
  if (view === "customers") return <CustomersView />;
  if (view === "products") return <ProductsView />;
  if (view === "promotions") return <PromotionsView />;
  if (view === "policies") return <PoliciesView />;
  if (view === "evaluation") return <EvaluationView />;
  if (view === "improvement") return <ImprovementView />;
  return <WorkspaceView />;
}

export default function HomePage() {
  return (
    <WorkspaceProvider>
      <div className="grid min-h-screen grid-cols-[224px_minmax(0,1fr)]">
        <Sidebar />
        <main className="min-w-0">
          <Topbar />
          <div className="mx-auto max-w-[1700px] px-7 py-6">
            <Router />
          </div>
        </main>
      </div>
      <Overlays />
    </WorkspaceProvider>
  );
}

