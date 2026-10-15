import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowRight, BookOpen, CalendarDays, Command, FolderOpen, Lightbulb, ListTodo, Search, Timer, X } from "lucide-react";
import { request } from "./api";
import type { Capability, CapabilityId } from "./capabilities";

type PinnedTemplate = { id: string; title: string; prompt: string; category: string; is_pinned: boolean };
const quickActions = [
  { label: "Create a task", detail: "Capture a clear next action", prompt: "Create a task called ", icon: ListTodo },
  { label: "Set a reminder", detail: "Remember something at the right time", prompt: "Remind me to ", icon: CalendarDays },
  { label: "Start focus", detail: "Begin a focused work session", prompt: "Start a focus session for ", icon: Timer },
  { label: "Find a document", detail: "Search your notes and writing", prompt: "Find my document about ", icon: BookOpen },
];

export function QuickOrin(props: {
  open: boolean; onClose: () => void; command: string; setCommand: (value: string) => void;
  submitCommand: (event: FormEvent) => Promise<void>; onSent: () => void; onCaptureIdea: () => void;
  navigate: (page: CapabilityId) => void; capabilities: Capability[]; page: CapabilityId;
  projectName?: string; taskName?: string; busy: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null); const [templates, setTemplates] = useState<PinnedTemplate[]>([]);
  useEffect(() => { if (!props.open) return; void request<PinnedTemplate[]>("/intelligence/templates").then(items => setTemplates(items.filter(item => item.is_pinned))).catch(() => setTemplates([])); window.setTimeout(() => inputRef.current?.focus(), 0); }, [props.open]);
  const query = props.command.trim().toLowerCase();
  const pages = useMemo(() => props.capabilities.filter(item => item.id !== "settings" && (!query || `${item.label} ${item.description}`.toLowerCase().includes(query))), [props.capabilities, query]);
  const actions = quickActions.filter(item => !query || `${item.label} ${item.detail}`.toLowerCase().includes(query));
  const pinned = templates.filter(item => !query || `${item.title} ${item.category}`.toLowerCase().includes(query));
  const choosePrompt = (value: string) => { props.setCommand(value); window.setTimeout(() => inputRef.current?.focus(), 0); };
  if (!props.open) return null;
  return <div className="quick-orin-layer"><button className="quick-orin-scrim" aria-label="Close Quick Orin" onClick={props.onClose} /><section className="quick-orin" role="dialog" aria-modal="true" aria-labelledby="quick-orin-title">
    <header><span className="brand-mark"><Command size={16} /></span><div><span className="eyebrow">QUICK ORIN</span><h2 id="quick-orin-title">Ask or go anywhere</h2></div><button className="toolbar-icon" aria-label="Close Quick Orin" onClick={props.onClose}><X size={17} /></button></header>
    <form onSubmit={(event) => { void props.submitCommand(event); props.onSent(); }}><Search size={18} /><input ref={inputRef} aria-label="Quick Orin command" value={props.command} onChange={event => props.setCommand(event.target.value)} placeholder="Ask Orin or search actions" /><button type="submit" disabled={!props.command.trim() || props.busy} aria-label="Send to Orin"><ArrowRight size={17} /></button></form>
    <p className="quick-orin-context">Current context: {props.page}{props.projectName ? ` · ${props.projectName}` : ""}{props.taskName ? ` · ${props.taskName}` : ""}</p>
    <div className="quick-orin-results">
      {pinned.length > 0 && <section><h3>Pinned workflows</h3>{pinned.map(item => <button key={item.id} onClick={() => choosePrompt(item.prompt)}><Lightbulb size={16} /><span><strong>{item.title}</strong><small>{item.category}</small></span></button>)}</section>}
      <section><h3>Quick actions</h3><button onClick={() => { props.onCaptureIdea(); props.onClose(); }}><Lightbulb size={16} /><span><strong>Capture an idea</strong><small>Save a thought to Writing</small></span></button>{actions.map(item => { const Icon = item.icon; return <button key={item.label} onClick={() => choosePrompt(item.prompt)}><Icon size={16} /><span><strong>{item.label}</strong><small>{item.detail}</small></span></button>; })}</section>
      <section><h3>Navigate</h3>{pages.slice(0, 6).map(item => <button key={item.id} onClick={() => { props.navigate(item.id); props.onClose(); }}><FolderOpen size={16} /><span><strong>{item.label}</strong><small>{item.description}</small></span></button>)}</section>
      {query && pinned.length === 0 && actions.length === 0 && pages.length === 0 && <p className="inline-empty">Press Enter to ask Orin.</p>}
    </div>
    <footer><span><kbd>Ctrl</kbd> <kbd>K</kbd> to open</span><span><kbd>Esc</kbd> to close</span></footer>
  </section></div>;
}
