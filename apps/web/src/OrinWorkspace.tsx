import type { FormEvent, ReactNode } from "react";
import { Command, Library, MessageCircle, Plus } from "lucide-react";
import type { AIModel } from "./AIModelsSettings";
import type { CommandResult, Conversation, Project, Task } from "./api";
import { TemplateLibrary } from "./TemplateLibrary";

type ChatTurn = { prompt: string; result: CommandResult };

type Starter = { label: string; prompt: string };

export function OrinWorkspace(props: {
  command: string; setCommand: (value: string) => void; submitCommand: (event: FormEvent) => void;
  busy: boolean; message: string; turns: ChatTurn[]; conversations: Conversation[];
  conversationId: string | null; openConversation: (id: string) => Promise<void>; newConversation: () => void;
  projects: Project[]; tasks: Task[]; projectId: string; setProjectId: (value: string) => void;
  taskId: string; setTaskId: (value: string) => void; models: AIModel[]; modelId: string; setModelId: (value: string) => void;
  starters: Starter[]; templatesOpen: boolean; setTemplatesOpen: (value: boolean) => void;
  renderAnswer: (result: CommandResult) => ReactNode;
}) {
  const activeConversation = props.conversations.find(item => item.id === props.conversationId);
  return <section className="orin-workspace" aria-label="Orin Workspace">
    <aside className="orin-workspace-sidebar"><header><span className="brand-mark"><Command size={16} /></span><div><span className="eyebrow">PERSONAL INTELLIGENCE</span><h1>Orin</h1></div></header><button className="primary-button" onClick={props.newConversation}><Plus size={15} />New session</button><h2>Recent work</h2><div className="orin-session-list">{props.conversations.slice(0, 20).map(item => <button className={item.id === props.conversationId ? "is-active" : ""} key={item.id} onClick={() => void props.openConversation(item.id)}><strong>{item.title}</strong><small>{new Date(item.updated_at).toLocaleDateString()}</small></button>)}</div></aside>
    <main className="orin-workspace-main"><header><div><span className="eyebrow">WORK SESSION</span><h2>{activeConversation?.title || "What are we working on?"}</h2><p>{activeConversation?.objective || "Ask, plan, review, and take action with your workspace context."}</p></div><button className="secondary-button" data-orin-control="orin-templates" onClick={() => props.setTemplatesOpen(!props.templatesOpen)}><Library size={15} />Templates</button></header>
      {props.templatesOpen && <TemplateLibrary page="" onClose={() => props.setTemplatesOpen(false)} onUse={value => { props.setCommand(value); props.setTemplatesOpen(false); }} />}
      <div className="orin-workspace-thread" aria-live="polite">{props.turns.length === 0 ? <div className="orin-workspace-welcome"><MessageCircle size={24} /><h3>Start with what you need</h3><div className="chat-starters">{props.starters.map(item => <button key={item.label} onClick={() => props.setCommand(item.prompt)}>{item.label}</button>)}</div></div> : props.turns.map(turn => <article className="chat-turn" key={turn.result.command_id}><div className="chat-user-message"><span className="eyebrow">YOU</span><p>{turn.prompt}</p></div>{props.renderAnswer(turn.result)}</article>)}{props.busy && <p role="status">Orin is thinking…</p>}{props.message && <p className="api-error" role="alert">{props.message}</p>}</div>
      <form className="orin-workspace-composer" onSubmit={props.submitCommand}><textarea aria-label="Ask Orin" rows={3} value={props.command} onChange={event => props.setCommand(event.target.value)} placeholder="Ask Orin what you need" /><div><select aria-label="AI model" value={props.modelId} onChange={event => props.setModelId(event.target.value)}>{props.models.map(model => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select><button className="primary-button" disabled={props.busy || !props.command.trim()}>Send</button></div></form>
    </main>
    <aside className="orin-workspace-context"><span className="eyebrow">LIVE CONTEXT</span><h2>Workspace context</h2><label>Project<select value={props.projectId} onChange={event => props.setProjectId(event.target.value)}><option value="">No project</option>{props.projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Task<select value={props.taskId} onChange={event => props.setTaskId(event.target.value)}><option value="">No task</option>{props.tasks.filter(item => !props.projectId || item.project_id === props.projectId).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><p>Orin receives this selection, the current page, conversation history, relevant memories, and authorized workspace records.</p></aside>
  </section>;
}
