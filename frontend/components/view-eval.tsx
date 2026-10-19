"use client";
import { EVAL_SCENARIOS } from "@/lib/mock-eval";
import { useWorkspace } from "@/components/workspace-provider";

export function EvaluationView() {
  const w = useWorkspace();
  const stats = [
    { l: "Task Success Rate", v: "82.4%", s: "Illustrative · 28 / 34 scenarios" },
    { l: "Resolution Quality", v: "4.2 / 5", s: "Illustrative rubric score" },
    { l: "Handoff rate", v: "11.8%", s: "Illustrative · includes expected handoffs" },
  ];
  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <div><div className="text-[11px] font-extrabold uppercase text-[#3859d7]">Quality overview</div>
        <h1 className="text-[25px] font-bold">Evaluation</h1>
        <p className="text-[13px] text-[#6b7788]">Illustrative scenarios — no backend connected.</p></div>
        <button type="button" onClick={() => {
          const blob = new Blob([JSON.stringify({ notice: "Illustrative demo data", scenarios: EVAL_SCENARIOS }, null, 2)], { type: "application/json" });
          const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
          a.download = "sc2026-demo-evaluation.json"; a.click(); URL.revokeObjectURL(a.href);
          w.showToast("Demo summary exported.");
        }} className="rounded-[10px] border bg-white px-3 py-2 font-semibold">↓ Export demo summary</button>
      </div>
      <div className="mb-4 grid grid-cols-3 gap-3.5 max-[850px]:grid-cols-1">
        {stats.map((s) => (
          <div key={s.l} className="rounded-[14px] border bg-white p-4">
            <div className="text-xs text-[#6b7788]">{s.l}</div>
            <strong className="mt-2 block text-2xl">{s.v}</strong><small className="text-[11px] text-[#6b7788]">{s.s}</small>
          </div>
        ))}
      </div>
      <div className="overflow-hidden rounded-2xl border bg-white">
        <div className="flex items-center justify-between border-b px-4 py-4">
          <div><h2 className="text-[15px] font-semibold">Scenario runs</h2><div className="text-[11px] text-[#6b7788]">Example cases</div></div>
          <span className="rounded-full bg-[#fff4dc] px-2.5 py-1 text-[11px] font-bold">ILLUSTRATIVE</span>
        </div>
        <table className="w-full border-collapse text-xs">
          <thead><tr className="bg-[#fbfcfe] text-left text-[10px] uppercase text-[#7d8797]">
            <th className="border-b px-3.5 py-3">Scenario</th><th className="border-b px-3.5 py-3">Focus</th>
            <th className="border-b px-3.5 py-3">Mode</th><th className="border-b px-3.5 py-3">Outcome</th><th className="border-b px-3.5 py-3">Evidence</th>
          </tr></thead>
          <tbody>
            {EVAL_SCENARIOS.map((s) => (
              <tr key={s.id}>
                <td className="border-b px-3.5 py-3"><strong>{s.id} · {s.id === "SC-01" ? "Returning customer" : s.id === "SC-04" ? "Channel switch" : s.id === "SC-07" ? "Policy boundary" : "Escalation"}</strong></td>
                <td className="border-b px-3.5 py-3">{s.focus}</td><td className="border-b px-3.5 py-3">{s.mode}</td>
                <td className="border-b px-3.5 py-3"><span className={`rounded-md px-2 py-1 text-[10px] font-bold ${s.outcome === "Pass" ? "bg-[#e7f7ee] text-[#148052]" : "bg-[#fff3dc] text-[#a56809]"}`}>{s.outcome}</span></td>
                <td className="border-b px-3.5 py-3"><button type="button" className="font-bold text-[#3859d7]" onClick={() =>
                  w.openModal({ title: `Scenario evidence · ${s.id}`, confirmText: "Close",
                    body: <p className="text-xs">Illustrative only. Review transcript vs success criteria. Source: seeded mock, no trace connected.</p> })}>View details ↗</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ImprovementView() {
  const cards = [
    { i: "↻", t: "Review recurring issues", d: "Identify where customers repeat information or continuity is lost.", tag: "Proposed" },
    { i: "✧", t: "Memory proposals", d: "Candidate memory changes for authorized human review before approval.", tag: "Human approval required" },
    { i: "◎", t: "Compare iterations", d: "Compare scenario evidence across baseline and improved configs.", tag: "Not connected" },
  ];
  return (
    <div>
      <div className="mb-4"><div className="text-[11px] font-extrabold uppercase text-[#3859d7]">Continuous improvement</div>
      <h1 className="text-[25px] font-bold">Improvement</h1>
      <p className="text-[13px] text-[#6b7788]">Proposed space for reviewing patterns.</p></div>
      <div className="grid grid-cols-3 gap-3.5 max-[850px]:grid-cols-1">
        {cards.map((c) => (
          <div key={c.t} className="rounded-[15px] border bg-white p-4">
            <div className="grid h-7 w-7 place-items-center rounded-[9px] bg-[#f0f3ff] text-[#3859d7]">{c.i}</div>
            <h2 className="mt-3 text-[15px] font-semibold">{c.t}</h2>
            <p className="mb-3 mt-1.5 text-[11px] text-[#6b7788]">{c.d}</p>
            <span className="rounded-md bg-[#f1f4f8] px-2 py-1 text-[10px] font-bold">{c.tag}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
