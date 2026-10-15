import { useEffect, useMemo, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Map, X } from "lucide-react";
import type { CapabilityId } from "./capabilities";

type GuideStep = { page: CapabilityId; control: string; title: string; instruction: string; completionEvent?: "click" | "change" };
type Guide = { id: string; title: string; description: string; steps: GuideStep[] };

export const GUIDES: Guide[] = [
  { id: "navigate", title: "Get around Orin", description: "Learn the main workspace and assistant areas.", steps: [
    { page: "home", control: "nav-home", title: "Your home", instruction: "Home summarizes current priorities, projects, tasks, and recent work.", completionEvent: "click" },
    { page: "orin", control: "nav-orin", title: "Orin Workspace", instruction: "Open the full assistant workspace for longer planning and continuing saved sessions.", completionEvent: "click" },
  ] },
  { id: "ai-models", title: "Configure an AI provider", description: "Connect a provider and select a model.", steps: [
    { page: "settings", control: "ai-model-settings", title: "AI providers and models", instruction: "Add a provider credential here. Orin encrypts it on the server and never shows it again." },
    { page: "settings", control: "ai-model-settings", title: "Verify and choose a model", instruction: "Test the connection, discover models, enable the ones you want, and mark a default." },
  ] },
  { id: "notifications", title: "Configure notifications", description: "Choose when and how Orin should alert you.", steps: [
    { page: "settings", control: "notification-settings", title: "Notification preferences", instruction: "Choose categories, quiet hours, repeat limits, and focus behavior in this section." },
  ] },
  { id: "project", title: "Start a project", description: "Create an outcome and organize its work.", steps: [
    { page: "projects", control: "projects-workspace", title: "Projects", instruction: "Create a project around an outcome, then add milestones, tasks, risks, and supporting knowledge." },
  ] },
  { id: "tasks", title: "Plan and complete tasks", description: "Turn priorities into concrete next actions.", steps: [
    { page: "tasks", control: "tasks-workspace", title: "Tasks", instruction: "Create, prioritize, schedule, and complete the next actions that move your projects forward." },
  ] },
  { id: "calendar", title: "Plan time on your calendar", description: "Schedule work and review your commitments.", steps: [
    { page: "calendar", control: "calendar-workspace", title: "Calendar", instruction: "Schedule task time, add events, and review your plan across month and week views." },
  ] },
  { id: "templates", title: "Use a guided workflow", description: "Find and run contextual templates.", steps: [
    { page: "orin", control: "orin-templates", title: "Workflow templates", instruction: "Open Templates to search built-in workflows or create and pin your own.", completionEvent: "click" },
  ] },
];

const progressKey = "orin.guided-progress.v1";

export function GuidedMode({ open, onClose, navigate }: { open: boolean; onClose: () => void; navigate: (page: CapabilityId) => void }) {
  const [guideId, setGuideId] = useState<string | null>(null); const [stepIndex, setStepIndex] = useState(0);
  const [completed, setCompleted] = useState<string[]>(() => { if (typeof window === "undefined") return []; try { return JSON.parse(window.localStorage.getItem(progressKey) || "[]") as string[]; } catch { return []; } });
  const guide = useMemo(() => GUIDES.find(item => item.id === guideId) ?? null, [guideId]); const step = guide?.steps[stepIndex];
  useEffect(() => {
    if (!open || !step) return;
    navigate(step.page);
    let target: HTMLElement | null = null; let timer = 0;
    const completeCurrentStep = () => {
      if (!guide) return;
      if (stepIndex < guide.steps.length - 1) setStepIndex(value => value + 1);
      else {
        setCompleted(current => {
          const next = [...new Set([...current, guide.id])];
          window.localStorage.setItem(progressKey, JSON.stringify(next));
          return next;
        });
        setGuideId(null); setStepIndex(0);
      }
    };
    const locate = () => { target = document.querySelector<HTMLElement>(`[data-orin-control="${step.control}"]`); if (!target) { timer = window.setTimeout(locate, 100); return; } target.classList.add("orin-guided-highlight"); target.scrollIntoView({ behavior: "smooth", block: "center" }); if (step.completionEvent) target.addEventListener(step.completionEvent, completeCurrentStep, { once: true }); };
    locate();
    return () => { window.clearTimeout(timer); target?.classList.remove("orin-guided-highlight"); if (step.completionEvent) target?.removeEventListener(step.completionEvent, completeCurrentStep); };
  }, [open, guide, stepIndex, step, navigate]);
  if (!open) return null;
  const finish = () => { if (!guide) return; const next = [...new Set([...completed, guide.id])]; setCompleted(next); if (typeof window !== "undefined") window.localStorage.setItem(progressKey, JSON.stringify(next)); setGuideId(null); setStepIndex(0); };
  const next = () => { if (!guide) return; if (stepIndex >= guide.steps.length - 1) finish(); else setStepIndex(value => value + 1); };
  return <aside className="guided-mode" role="dialog" aria-modal="false" aria-labelledby="guided-title"><header><span className="brand-mark"><Map size={16} /></span><div><span className="eyebrow">GUIDED MODE</span><h2 id="guided-title">{guide?.title || "What would you like to learn?"}</h2></div><button className="toolbar-icon" aria-label="Close Guided Mode" onClick={onClose}><X size={17} /></button></header>
    {!guide ? <div className="guided-list">{GUIDES.map(item => <button key={item.id} onClick={() => { setGuideId(item.id); setStepIndex(0); }}><span>{completed.includes(item.id) ? <Check size={16} /> : <Map size={16} />}</span><div><strong>{item.title}</strong><p>{item.description}</p></div><ChevronRight size={16} /></button>)}</div> : <div className="guided-step"><span>Step {stepIndex + 1} of {guide.steps.length}</span><h3>{step?.title}</h3><p>{step?.instruction}</p><div><button className="secondary-button" onClick={() => stepIndex ? setStepIndex(value => value - 1) : setGuideId(null)}><ChevronLeft size={15} />Back</button><button className="primary-button" onClick={next}>{stepIndex === guide.steps.length - 1 ? "Finish" : "Next"}<ChevronRight size={15} /></button></div></div>}
  </aside>;
}
