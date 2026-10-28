import type { Project } from "./api";
import { KnowledgeWorkspace } from "./KnowledgeWorkspace";

export function WritingStudio({
  projects,
  userId,
  onOpenTask,
}: {
  projects: Project[];
  userId: string;
  onOpenTask: (id: string) => void;
}) {
  return (
    <div className="writing-studio">
      <div className="studio-surface">
        <KnowledgeWorkspace projects={projects} userId={userId} onOpenTask={onOpenTask} />
      </div>
    </div>
  );
}
