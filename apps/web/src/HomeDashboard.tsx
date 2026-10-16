import type { CSSProperties, FormEvent, ReactNode } from "react";
import { ArrowRight, BookOpen, CalendarDays, Check, ChevronRight, FileText, GraduationCap, Lightbulb, MessageCircle, Paperclip, PenLine, Plus, Search, Send, Sparkles, Target, Zap } from "lucide-react";
import type { Attachment, Conversation, Project, Task, User } from "./api";
import "./home-dashboard.css";

type Props = {
  user: User;
  tasks: Task[];
  projects: Project[];
  conversations: Conversation[];
  files: Attachment[];
  command: string;
  setCommand: (value: string) => void;
  submitCommand: (event: FormEvent) => void | Promise<void>;
  busy: boolean;
  openAssistant: (prompt?: string) => void;
  openTask: (id: string) => void;
  openProject: (id: string) => void;
  openPage: (page: "tasks" | "projects" | "memories" | "calendar" | "orin" | "activity") => void;
  capture: () => void;
  children?: ReactNode;
};

const timeGreeting = () => {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
};

export function HomeDashboard(props: Props) {
  const openTasks = props.tasks.filter(task => !["done", "cancelled"].includes(task.status)).slice(0, 5);
  const completed = props.tasks.filter(task => task.status === "done").length;
  const focusTotal = Math.max(5, Math.min(12, props.tasks.length || 5));
  const focusDone = Math.min(focusTotal, completed);
  const activeProjects = props.projects.filter(project => project.status === "active").slice(0, 5);
  const quickPrompt = (prompt: string) => { props.setCommand(prompt); props.openAssistant(prompt); };
  return <div className="orin-home">
    <section className="home-hero">
      <div className="hero-copy"><p>{timeGreeting()}, {props.user.display_name.split(" ")[0]}</p><h1>What would you like to<br />work on today?</h1><span>Ask Orin, plan your day, or jump into a project.</span></div>
      <p className="hero-mantra">Better tools.<br />Deeper focus.<br />Greater impact.</p>
      <form className="hero-composer" onSubmit={event => { void props.submitCommand(event); props.openAssistant(); }}>
        <Sparkles size={20} /><input aria-label="Ask Orin from home" value={props.command} onChange={event => props.setCommand(event.target.value)} placeholder="Ask Orin anything…" />
        <button type="button" aria-label="Add attachment" onClick={props.capture}><Paperclip size={18} /></button>
        <button className="hero-send" aria-label="Send to Orin" disabled={props.busy || !props.command.trim()}><Send size={18} /></button>
      </form>
      <div className="hero-actions">
        <button onClick={() => quickPrompt("Help me plan my day")}><CalendarDays size={15} />Plan my day</button>
        <button onClick={() => props.openPage("memories")}><PenLine size={15} />Write something</button>
        <button onClick={() => quickPrompt("Search my workspace and summarize what matters") }><Search size={15} />Search my workspace</button>
        <button onClick={() => quickPrompt("Help me build my next project step by step") }><Zap size={15} />Help me build</button>
      </div>
    </section>

    <section className="home-mode-grid" aria-label="Workspace shortcuts">
      <button onClick={props.capture}><span><Plus size={18} /></span><strong>Capture</strong><small>Save ideas, links, and notes</small><ChevronRight size={17} /></button>
      <button onClick={() => props.openPage("calendar")}><span><CalendarDays size={18} /></span><strong>Plan</strong><small>Organize your day and goals</small><ChevronRight size={17} /></button>
      <button onClick={() => props.openPage("memories")}><span><Lightbulb size={18} /></span><strong>Create</strong><small>Write, design, build, and edit</small><ChevronRight size={17} /></button>
      <button onClick={() => props.openPage("orin")}><span><GraduationCap size={18} /></span><strong>Learn</strong><small>Grow with guided assistance</small><ChevronRight size={17} /></button>
    </section>

    <div className="home-content-grid">
      <div className="home-primary-column">
        <section className="dashboard-card today-card">
          <header><div><CalendarDays size={18} /><h2>Today</h2><small>{new Date().toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</small></div><button onClick={() => props.openPage("tasks")}>View all</button></header>
          <div className="compact-list">{openTasks.length ? openTasks.map((task, index) => <button key={task.id} onClick={() => props.openTask(task.id)}><span className={`task-dot ${index === 0 ? "active" : ""}`}>{index === 0 && <Check size={12} />}</span><strong>{task.title}</strong><small>{task.due_at ? new Date(task.due_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : task.priority}</small><ChevronRight size={15} /></button>) : <p className="dashboard-empty">Your day is clear. Capture one meaningful next step.</p>}</div>
        </section>
        <section className="dashboard-card projects-card">
          <header><div><Target size={18} /><h2>Recent Projects</h2></div><button onClick={() => props.openPage("projects")}>View all</button></header>
          <div className="project-rows">{activeProjects.length ? activeProjects.map((project, index) => <button key={project.id} onClick={() => props.openProject(project.id)}><span className={`project-glyph tone-${index % 4}`}><Target size={15} /></span><span><strong>{project.name}</strong><small>{project.objective || project.description || "Ready for a clear next outcome"}</small></span><em>{project.status === "active" ? "In progress" : project.status}</em><ChevronRight size={15} /></button>) : <p className="dashboard-empty">Active projects will appear here.</p>}</div>
        </section>
      </div>

      <div className="home-secondary-column">
        <section className="dashboard-card quick-card"><header><div><Zap size={18} /><h2>Quick Access</h2></div></header><div className="quick-rows">
          {activeProjects.slice(0, 3).map((project, index) => <button key={project.id} onClick={() => props.openProject(project.id)}><span className={`project-glyph tone-${index % 4}`}><Target size={14} /></span><span><strong>{project.name}</strong><small>{project.objective || "Project workspace"}</small></span><ChevronRight size={15} /></button>)}
          <button onClick={() => props.openPage("memories")}><span className="project-glyph"><BookOpen size={14} /></span><span><strong>Knowledge Base</strong><small>Notes, guides, resources</small></span><ChevronRight size={15} /></button>
          <button onClick={props.capture}><span className="project-glyph"><FileText size={14} /></span><span><strong>Files</strong><small>Recent files and uploads</small></span><ChevronRight size={15} /></button>
        </div></section>
        <section className="dashboard-card activity-card"><header><div><Sparkles size={18} /><h2>Activity</h2></div><button onClick={() => props.openPage("activity")}>View all</button></header><div className="activity-rows">{props.conversations.slice(0, 5).map(item => <button key={item.id} onClick={() => props.openAssistant()}><MessageCircle size={15} /><span><strong>{item.title || "Orin work session"}</strong><small>{new Date(item.updated_at).toLocaleString()}</small></span></button>)}{!props.conversations.length && <p className="dashboard-empty">Your recent Orin sessions will appear here.</p>}</div></section>
      </div>

      <aside className="home-right-rail">
        <section className="dashboard-card assistant-card"><header><div><Sparkles size={20} /><h2>AI Assistant</h2></div></header><p>Your thinking partner, always here.</p>{["Help me plan my week", "Write a social media post", "Summarize this document", "Explain this in simple terms"].map(prompt => <button key={prompt} onClick={() => quickPrompt(prompt)}>{prompt}<ChevronRight size={15} /></button>)}<button className="rail-ask" onClick={() => props.openAssistant()}>Ask Orin anything…<ArrowRight size={16} /></button></section>
        <section className="dashboard-card focus-card"><header><div><Target size={20} /><h2>Focus</h2></div></header><p>You’re making progress!</p><div className="focus-summary"><div className="focus-ring" style={{ "--progress": `${Math.max(10, focusDone / focusTotal * 100)}%` } as CSSProperties}><span /></div><strong>{focusDone}/{focusTotal}<small>key goals completed</small></strong></div><button onClick={() => props.openPage("tasks")}>View goals <ArrowRight size={15} /></button></section>
        <section className="dashboard-card files-card"><header><div><FileText size={18} /><h2>Recent Files</h2></div><button onClick={props.capture}>Add</button></header>{props.files.slice(0, 5).map(file => <button key={file.id} onClick={() => props.openAssistant()}><FileText size={16} /><span><strong>{file.filename}</strong><small>{file.media_type}</small></span></button>)}{!props.files.length && <p className="dashboard-empty">Files shared with Orin will appear here.</p>}</section>
      </aside>
    </div>
    {props.children && <details className="home-intelligence-tools"><summary>More intelligence tools</summary><div>{props.children}</div></details>}
  </div>;
}
