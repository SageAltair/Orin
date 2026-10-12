import { useRef, useState } from "react";
import { BookOpen, Lightbulb, Network, Layers } from "lucide-react";
import type { Project } from "./api";
import { KnowledgeWorkspace } from "./KnowledgeWorkspace";
import { IdeaInbox } from "./features/creative-studio/IdeaInbox";
import { IdeasCanvas } from "./features/creative-studio/IdeasCanvas";
import { Manuscript } from "./features/creative-studio/Manuscript";

const tabs = [
  { id: "notes", label: "Notes", icon: BookOpen },
  { id: "ideas", label: "Idea inbox", icon: Lightbulb },
  { id: "canvas", label: "Connections", icon: Network },
  { id: "manuscript", label: "Manuscript", icon: Layers },
] as const;

export function WritingStudio({
  projects,
  userId,
  onOpenTask,
}: {
  projects: Project[];
  userId: string;
  onOpenTask: (id: string) => void;
}) {
  const [tab, setTab] = useState<string>("notes");
  const flush = useRef<(() => Promise<boolean>) | null>(null);
  const navigate = async (next: string) => {
    if (tab === "notes" && flush.current && !(await flush.current())) return;
    setTab(next);
  };
  return (
    <div className="writing-studio">
      <header className="writing-studio-heading">
        <div>
          <span className="eyebrow">YOUR CREATIVE WORKSPACE</span>
          <h1>Writing</h1>
          <p>A quiet place to think. Room to build something bigger.</p>
        </div>
        <span className="studio-private">
          <span /> Private workspace
        </span>
      </header>
      <nav className="studio-tabs" aria-label="Writing views">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            type="button"
            key={id}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => void navigate(id)}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>
      <div className="studio-surface">
        {tab === "notes" && (
          <KnowledgeWorkspace
            projects={projects}
            userId={userId}
            onOpenTask={onOpenTask}
            onSaveReady={(save) => {
              flush.current = save;
            }}
          />
        )}
        {tab === "ideas" && <IdeaInbox onOpenCanvas={() => setTab("canvas")} />}
        {tab === "canvas" && <IdeasCanvas />}
        {tab === "manuscript" && <Manuscript projects={projects} />}
      </div>
    </div>
  );
}
