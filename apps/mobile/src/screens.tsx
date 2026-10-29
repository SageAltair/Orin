import { useEffect, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { errorMessage, login, register, request } from "./api";
import { fetchAllMobileTasks } from "./task-pagination";
import { dueAtForMobileEdit, filterMobileTasks, toLocalTaskDateTime, toUtcTaskDueAt, type MobileTaskView } from "./task-planning";
import type { Palette } from "./theme";
import type {
  CommandResult,
  Note,
  OperationsKey,
  Project,
  Task,
  User,
  Workspace,
} from "./types";
import {
  Card,
  EmptyState,
  ErrorNotice,
  Eyebrow,
  Field,
  PrimaryButton,
  Screen,
  SecondaryButton,
  SectionTitle,
  Sheet,
} from "./ui";
import { OperationsScreen } from "./operations";
import { Icon, type IconName } from "./icons";

export function AuthScreen({
  colors,
  onAuthenticated,
}: {
  colors: Palette;
  onAuthenticated: (user: User) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      onAuthenticated(
        mode === "login"
          ? await login(email, password)
          : await register(email, password, name),
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={local.auth}
      keyboardShouldPersistTaps="handled"
    >
      <View style={local.brandMark}>
        <Icon name="brand" color={colors.accent} size={36} />
        <Text style={[local.brand, { color: colors.text }]}>orin</Text>
      </View>
      <View style={local.authIntro}>
        <Eyebrow colors={colors}>Your life, organized</Eyebrow>
        <Text style={[local.authTitle, { color: colors.text }]}>
          {mode === "login" ? "Welcome back." : "Start with clarity."}
        </Text>
        <Text style={[local.authCopy, { color: colors.muted }]}>
          Your personal workspace for focused work, projects, writing and
          AI-assisted execution.
        </Text>
      </View>
      <Card colors={colors} style={local.authCard}>
        {mode === "register" && (
          <Field
            label="Your name"
            colors={colors}
            value={name}
            onChangeText={setName}
            autoCapitalize="words"
          />
        )}
        <Field
          label="Email"
          colors={colors}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          autoComplete="email"
        />
        <Field
          label="Password"
          colors={colors}
          value={password}
          onChangeText={setPassword}
          secureTextEntry={!showPassword}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
        <Pressable accessibilityRole="button" onPress={() => setShowPassword(value => !value)} style={local.passwordToggle}>
          <Text style={[local.passwordToggleText, { color: colors.accent }]}>{showPassword ? "Hide password" : "Show password"}</Text>
        </Pressable>
        <ErrorNotice message={error} colors={colors} />
        <PrimaryButton
          label={
            busy
              ? "Please wait…"
              : mode === "login"
                ? "Sign in"
                : "Create account"
          }
          onPress={() => void submit()}
          colors={colors}
          disabled={
            busy ||
            !email.trim() ||
            password.length < 8 ||
            (mode === "register" && !name.trim())
          }
        />
        <Pressable
          onPress={() => {
            setMode((value) => (value === "login" ? "register" : "login"));
            setError("");
          }}
        >
          <Text style={[local.switchAuth, { color: colors.accent }]}>
            {mode === "login"
              ? "New to Orin? Create an account"
              : "Already have an account? Sign in"}
          </Text>
        </Pressable>
      </Card>
    </ScrollView>
  );
}

export function HomeScreen({
  colors,
  user,
  workspace,
  active,
  onDataChanged,
}: {
  colors: Palette;
  user: User;
  workspace: Workspace | null;
  active: boolean;
  onDataChanged: () => void;
}) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [prompt, setPrompt] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextTasks, nextProjects] = await Promise.all([
        request<Task[]>("/tasks?limit=100"),
        request<Project[]>("/projects"),
      ]);
      setTasks(nextTasks);
      setProjects(nextProjects);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (active) void load();
  }, [active, workspace?.id]);
  const ask = async () => {
    if (!prompt.trim()) return;
    setBusy(true);
    setError("");
    setAnswer("");
    try {
      const result = await request<CommandResult>("/commands", {
        method: "POST",
        body: JSON.stringify({ text: prompt.trim() }),
      });
      setAnswer(result.message);
      setPrompt("");
      onDataChanged();
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const open = tasks.filter(
    (task) => !["done", "cancelled"].includes(task.status),
  );
  return (
    <Screen colors={colors} refreshing={loading}>
      <View style={local.hero}>
        <Eyebrow colors={colors}>{workspace?.name ?? "PERSONAL"}</Eyebrow>
        <Text style={[local.heroTitle, { color: colors.text }]}>
          Good {greeting()}, {user.display_name.split(" ")[0]}.
        </Text>
        <Text style={[local.heroCopy, { color: colors.muted }]}>
          What would you like to move forward today?
        </Text>
      </View>
      <Card
        colors={colors}
        style={[local.askCard, { backgroundColor: colors.accentSoft }]}
      >
        <Text style={[local.askLabel, { color: colors.accent }]}>Ask Orin</Text>
        <TextInput
          accessibilityLabel="Ask Orin"
          value={prompt}
          onChangeText={setPrompt}
          multiline
          placeholder="Plan my day, capture a task, or ask a question…"
          placeholderTextColor={colors.muted}
          style={[local.askInput, { color: colors.text }]}
        />
        <View style={local.askFooter}>
          <Text style={[local.askHint, { color: colors.muted }]}>
            Natural language · approval-aware
          </Text>
          <PrimaryButton
            compact
            label={busy ? "Thinking…" : "Send"}
            onPress={() => void ask()}
            colors={colors}
            disabled={busy || !prompt.trim()}
          />
        </View>
      </Card>
      <ErrorNotice message={error} colors={colors} />
      {answer ? (
        <Card colors={colors}>
          <Eyebrow colors={colors}>Orin response</Eyebrow>
          <Text style={[local.answer, { color: colors.text }]}>{answer}</Text>
        </Card>
      ) : null}
      <Text style={[local.dailyContext, { color: colors.muted }]}>
        {open.length
          ? `${open.length} active ${open.length === 1 ? "task" : "tasks"} across ${projects.length} ${projects.length === 1 ? "project" : "projects"}.`
          : "No active tasks need your attention."}
      </Text>
      <SectionTitle colors={colors}>Up next</SectionTitle>
      {open.length ? (
        <Card colors={colors} style={local.listCard}>
          {open.slice(0, 5).map((task, index) => (
            <View
              key={task.id}
              style={[
                local.row,
                index > 0 && { borderTopColor: colors.line, borderTopWidth: 1 },
              ]}
            >
              <View
                style={[
                  local.taskDot,
                  {
                    borderColor:
                      task.priority === "urgent"
                        ? colors.danger
                        : colors.accent,
                  },
                ]}
              />
              <View style={local.rowCopy}>
                <Text
                  numberOfLines={2}
                  style={[local.rowTitle, { color: colors.text }]}
                >
                  {task.title}
                </Text>
                <Text style={[local.rowMeta, { color: colors.muted }]}>
                  {task.status.replace("_", " ")}
                  {task.estimated_minutes
                    ? ` · ${task.estimated_minutes} min`
                    : ""}
                </Text>
              </View>
            </View>
          ))}
        </Card>
      ) : (
        <EmptyState
          title="A clear desk"
          detail="Add a task or ask Orin to plan your next move."
          colors={colors}
        />
      )}
    </Screen>
  );
}

export function TasksScreen({
  colors,
  active,
  workspace,
  onTasksChanged,
}: {
  colors: Palette;
  active: boolean;
  workspace: Workspace | null;
  onTasksChanged?: () => void;
}) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [createDue, setCreateDue] = useState("");
  const [view, setView] = useState<MobileTaskView>("all");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Task | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editStatus, setEditStatus] = useState<Task["status"]>("todo");
  const [editPriority, setEditPriority] = useState<Task["priority"]>("normal");
  const [editDue, setEditDue] = useState("");
  const [saving, setSaving] = useState(false);
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setTasks(await fetchAllMobileTasks());
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (active) void load();
  }, [active, workspace?.id]);
  const create = async () => {
    if (!title.trim()) return;
    setCreating(true);
    setError("");
    try {
      await request<Task>("/tasks", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), due_at: toUtcTaskDueAt(createDue) }),
      });
      setTitle("");
      setCreateDue("");
      await load();
      onTasksChanged?.();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setCreating(false);
    }
  };
  const toggle = async (task: Task) => {
    const status = task.status === "done" ? "todo" : "done";
    setTasks((current) =>
      current.map((item) => (item.id === task.id ? { ...item, status } : item)),
    );
    try {
      await request<Task>(`/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      onTasksChanged?.();
    } catch (cause) {
      setError(errorMessage(cause));
      await load();
    }
  };
  const openTask = (task: Task) => {
    setEditing(task);
    setEditTitle(task.title);
    setEditDescription(task.description ?? "");
    setEditStatus(task.status);
    setEditPriority(task.priority);
    setEditDue(toLocalTaskDateTime(task.due_at));
    setError("");
  };
  const saveTask = async () => {
    if (!editing || !editTitle.trim()) return;
    setSaving(true);
    setError("");
    try {
      await request<Task>(`/tasks/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: editTitle.trim(),
          description: editDescription.trim() || null,
          status: editStatus,
          priority: editPriority,
          due_at: dueAtForMobileEdit(editDue, editing.due_at),
        }),
      });
      setEditing(null);
      await load();
      onTasksChanged?.();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSaving(false);
    }
  };
  const visible = filterMobileTasks(tasks, view, search);
  return (
    <Screen colors={colors} refreshing={loading}>
      <View>
        <Eyebrow colors={colors}>{workspace?.name ?? "PERSONAL"}</Eyebrow>
        <Text style={[local.pageTitle, { color: colors.text }]}>Tasks</Text>
      </View>
      <Card colors={colors} style={local.capture}>
        <View style={local.captureRow}>
          <TextInput
            accessibilityLabel="New task"
            value={title}
            onChangeText={setTitle}
            onSubmitEditing={() => void create()}
            returnKeyType="done"
            placeholder="Add a task…"
            placeholderTextColor={colors.muted}
            style={[local.captureInput, { color: colors.text }]}
          />
          <PrimaryButton
            compact
            label={creating ? "Adding…" : "Add"}
            onPress={() => void create()}
            colors={colors}
            disabled={creating || !title.trim()}
          />
        </View>
        <Field
          label="Due date and time (optional)"
          colors={colors}
          value={createDue}
          onChangeText={setCreateDue}
          autoCapitalize="none"
          placeholder="YYYY-MM-DDTHH:MM"
        />
      </Card>
      <ErrorNotice message={error} colors={colors} />
      <ChoiceRow
        label="View"
        values={["all", "today", "upcoming", "overdue", "completed"]}
        selected={view}
        onSelect={(value) => setView(value as MobileTaskView)}
        colors={colors}
      />
      <Field label="Search tasks" colors={colors} value={search} onChangeText={setSearch} />
      <View style={local.filterRow}>
        <SectionTitle colors={colors}>
          {visible.length} {visible.length === 1 ? "task" : "tasks"}
        </SectionTitle>
      </View>
      {visible.length ? (
        <Card colors={colors} style={local.listCard}>
          {visible.map((task, index) => (
            <View
              key={task.id}
              style={[
                local.row,
                index > 0 && { borderTopColor: colors.line, borderTopWidth: 1 },
              ]}
            >
              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: task.status === "done" }}
                accessibilityLabel={`Complete ${task.title}`}
                onPress={() => void toggle(task)}
              >
                <View
                  style={[
                    local.check,
                    {
                      borderColor:
                        task.status === "done" ? colors.teal : colors.line,
                      backgroundColor:
                        task.status === "done" ? colors.teal : "transparent",
                    },
                  ]}
                >
                  {task.status === "done" && <Icon name="check" size={14} color="#FFFFFF" strokeWidth={2.4} />}
                </View>
              </Pressable>
              <Pressable style={local.rowCopy} onPress={() => openTask(task)}>
                <Text
                  style={[
                    local.rowTitle,
                    {
                      color:
                        task.status === "done" ? colors.muted : colors.text,
                      textDecorationLine:
                        task.status === "done" ? "line-through" : "none",
                    },
                  ]}
                >
                  {task.title}
                </Text>
                <Text style={[local.rowMeta, { color: colors.muted }]}>
                  {task.priority} priority · {task.status.replace("_", " ")}
                  {task.due_at
                    ? ` · ${new Date(task.due_at).toLocaleString()}`
                    : ""}
                </Text>
              </Pressable>
              <Icon name="right" size={17} color={colors.muted} />
            </View>
          ))}
        </Card>
      ) : (
        <EmptyState
          title="No tasks here"
          detail="Capture the next concrete action. Keep it small and clear."
          colors={colors}
        />
      )}
      <Sheet
        visible={Boolean(editing)}
        title="Task details"
        onClose={() => setEditing(null)}
        colors={colors}
      >
        <ScrollView keyboardShouldPersistTaps="handled">
          <View style={local.sheetFields}>
            <Field
              label="Task title"
              colors={colors}
              value={editTitle}
              onChangeText={setEditTitle}
            />
            <Field
              label="Description"
              colors={colors}
              value={editDescription}
              onChangeText={setEditDescription}
              multiline
              placeholder="Context, definition of done, or next step…"
            />
            <ChoiceRow
              label="Status"
              values={["todo", "in_progress", "blocked", "done", "cancelled"]}
              selected={editStatus}
              onSelect={(value) => setEditStatus(value as Task["status"])}
              colors={colors}
            />
            <ChoiceRow
              label="Priority"
              values={["low", "normal", "high", "urgent"]}
              selected={editPriority}
              onSelect={(value) => setEditPriority(value as Task["priority"])}
              colors={colors}
            />
            <Field
              label="Due date and time (optional)"
              colors={colors}
              value={editDue}
              onChangeText={setEditDue}
              autoCapitalize="none"
              placeholder="YYYY-MM-DDTHH:MM"
            />
            <ErrorNotice message={error} colors={colors} />
            <PrimaryButton
              label={saving ? "Saving…" : "Save changes"}
              onPress={() => void saveTask()}
              colors={colors}
              disabled={saving || !editTitle.trim()}
            />
          </View>
        </ScrollView>
      </Sheet>
    </Screen>
  );
}

function ChoiceRow({
  label,
  values,
  selected,
  onSelect,
  colors,
}: {
  label: string;
  values: string[];
  selected: string;
  onSelect: (value: string) => void;
  colors: Palette;
}) {
  return (
    <View style={local.choiceWrap}>
      <Text style={[local.label, { color: colors.muted }]}>{label}</Text>
      <View style={local.choiceRow}>
        {values.map((value) => (
          <Pressable
            key={value}
            onPress={() => onSelect(value)}
            style={[
              local.choice,
              {
                borderColor: selected === value ? colors.accent : colors.line,
                backgroundColor:
                  selected === value ? colors.accentSoft : colors.surface,
              },
            ]}
          >
            <Text
              style={{
                color: selected === value ? colors.accent : colors.text,
                fontSize: 11,
                fontWeight: "600",
                textTransform: "capitalize",
              }}
            >
              {value.replace("_", " ")}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export function ProjectsScreen({
  colors,
  active,
  workspace,
}: {
  colors: Palette;
  active: boolean;
  workspace: Workspace | null;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sheet, setSheet] = useState(false);
  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Project | null>(null);
  const [projectTasks, setProjectTasks] = useState<Task[]>([]);
  const [projectName, setProjectName] = useState("");
  const [projectObjective, setProjectObjective] = useState("");
  const [projectStatus, setProjectStatus] =
    useState<Project["status"]>("active");
  const [taskTitle, setTaskTitle] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setProjects(await request<Project[]>("/projects"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (active) void load();
  }, [active, workspace?.id]);
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      await request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          objective: objective.trim() || null,
        }),
      });
      setName("");
      setObjective("");
      setSheet(false);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const openProject = async (project: Project) => {
    setSelected(project);
    setProjectName(project.name);
    setProjectObjective(project.objective ?? "");
    setProjectStatus(project.status);
    setError("");
    setLoading(true);
    try {
      setProjectTasks(
        await request<Task[]>(`/tasks?project_id=${project.id}&limit=100`),
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  const saveProject = async () => {
    if (!selected || !projectName.trim()) return;
    setBusy(true);
    setError("");
    try {
      const updated = await request<Project>(`/projects/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: projectName.trim(),
          objective: projectObjective.trim() || null,
          status: projectStatus,
        }),
      });
      setSelected(updated);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const addProjectTask = async () => {
    if (!selected || !taskTitle.trim()) return;
    setBusy(true);
    setError("");
    try {
      await request<Task>("/tasks", {
        method: "POST",
        body: JSON.stringify({
          title: taskTitle.trim(),
          project_id: selected.id,
        }),
      });
      setTaskTitle("");
      setProjectTasks(
        await request<Task[]>(`/tasks?project_id=${selected.id}&limit=100`),
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  if (selected)
    return (
      <Screen colors={colors} refreshing={loading}>
        <View style={local.editorTop}>
          <SecondaryButton
            compact
            label="Back"
            onPress={() => setSelected(null)}
            colors={colors}
          />
          <View style={local.projectDetailHeading}>
            <Eyebrow colors={colors}>Project</Eyebrow>
            <Text
              numberOfLines={1}
              style={[local.projectDetailTitle, { color: colors.text }]}
            >
              {selected.name}
            </Text>
          </View>
          <PrimaryButton
            compact
            label={busy ? "Saving…" : "Save"}
            onPress={() => void saveProject()}
            colors={colors}
            disabled={busy || !projectName.trim()}
          />
        </View>
        <Field
          label="Project name"
          colors={colors}
          value={projectName}
          onChangeText={setProjectName}
        />
        <Field
          label="Objective"
          colors={colors}
          value={projectObjective}
          onChangeText={setProjectObjective}
          multiline
          placeholder="Define the outcome this project creates…"
        />
        <ChoiceRow
          label="Status"
          values={[
            "planning",
            "active",
            "blocked",
            "paused",
            "completed",
            "archived",
          ]}
          selected={projectStatus}
          onSelect={(value) => setProjectStatus(value as Project["status"])}
          colors={colors}
        />
        <ErrorNotice message={error} colors={colors} />
        <SectionTitle colors={colors}>Project tasks</SectionTitle>
        <Card colors={colors} style={local.capture}>
          <TextInput
            accessibilityLabel="New project task"
            value={taskTitle}
            onChangeText={setTaskTitle}
            onSubmitEditing={() => void addProjectTask()}
            returnKeyType="done"
            placeholder="Add a task to this project…"
            placeholderTextColor={colors.muted}
            style={[local.captureInput, { color: colors.text }]}
          />
          <PrimaryButton
            compact
            label="Add"
            onPress={() => void addProjectTask()}
            colors={colors}
            disabled={busy || !taskTitle.trim()}
          />
        </Card>
        {projectTasks.length ? (
          <Card colors={colors} style={local.listCard}>
            {projectTasks.map((task, index) => (
              <View
                key={task.id}
                style={[
                  local.row,
                  index > 0 && {
                    borderTopWidth: 1,
                    borderTopColor: colors.line,
                  },
                ]}
              >
                <View
                  style={[
                    local.taskDot,
                    {
                      borderColor:
                        task.status === "done" ? colors.teal : colors.accent,
                    },
                  ]}
                />
                <View style={local.rowCopy}>
                  <Text style={[local.rowTitle, { color: colors.text }]}>
                    {task.title}
                  </Text>
                  <Text style={[local.rowMeta, { color: colors.muted }]}>
                    {task.status.replace("_", " ")} · {task.priority}
                  </Text>
                </View>
              </View>
            ))}
          </Card>
        ) : (
          <EmptyState
            title="No project tasks"
            detail="Add the first concrete action for this project."
            colors={colors}
          />
        )}
      </Screen>
    );
  return (
    <Screen colors={colors} refreshing={loading}>
      <View style={local.titleWithAction}>
        <View>
          <Eyebrow colors={colors}>{workspace?.name ?? "PERSONAL"}</Eyebrow>
          <Text style={[local.pageTitle, { color: colors.text }]}>
            Projects
          </Text>
        </View>
        <PrimaryButton
          compact
          label="New project"
          onPress={() => setSheet(true)}
          colors={colors}
        />
      </View>
      <ErrorNotice message={error} colors={colors} />
      {projects.length ? (
        <Card colors={colors} style={local.listCard}>
          {projects.map((project, index) => (
          <Pressable key={project.id} onPress={() => void openProject(project)} style={[local.projectListRow, index > 0 && { borderTopWidth: 1, borderTopColor: colors.line }]}>
              <View style={local.projectTop}>
                <View
                  style={[
                    local.projectGlyph,
                    { backgroundColor: colors.accentSoft },
                  ]}
                >
                  <Text style={{ color: colors.accent, fontWeight: "700" }}>
                    {project.name.slice(0, 1).toUpperCase()}
                  </Text>
                </View>
                <View style={local.rowCopy}>
                  <Text style={[local.projectName, { color: colors.text }]}>
                    {project.name}
                  </Text>
                  <Text style={[local.rowMeta, { color: colors.muted }]}>
                    {project.status} · {project.priority}
                  </Text>
                </View>
                <Icon name="right" size={17} color={colors.muted} />
              </View>
              {project.objective ? (
                <Text numberOfLines={2} style={[local.projectObjective, { color: colors.muted }]}>
                  {project.objective}
                </Text>
              ) : null}
          </Pressable>
          ))}
        </Card>
      ) : (
        <EmptyState
          title="No projects yet"
          detail="Create an outcome-focused workspace for related tasks and notes."
          colors={colors}
        />
      )}
      <Sheet
        visible={sheet}
        title="New project"
        onClose={() => setSheet(false)}
        colors={colors}
      >
        <View style={local.sheetFields}>
          <Field
            label="Project name"
            colors={colors}
            value={name}
            onChangeText={setName}
            autoFocus
          />
          <Field
            label="Objective"
            colors={colors}
            value={objective}
            onChangeText={setObjective}
            multiline
            placeholder="What will be different when this is complete?"
          />
          <ErrorNotice message={error} colors={colors} />
          <PrimaryButton
            label={busy ? "Creating…" : "Create project"}
            onPress={() => void create()}
            colors={colors}
            disabled={busy || !name.trim()}
          />
        </View>
      </Sheet>
    </Screen>
  );
}

const richPrefix = "<!--orin-rich-v1-->";
const plainText = (content: string) =>
  content.startsWith(richPrefix)
    ? content
        .slice(richPrefix.length)
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim()
    : content;
export function NotesScreen({
  colors,
  active,
}: {
  colors: Palette;
  active: boolean;
}) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [selected, setSelected] = useState<Note | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setNotes(await request<Note[]>("/knowledge/documents?limit=200"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (active && !selected) void load();
  }, [active]);
  const open = (note: Note) => {
    setSelected(note);
    setTitle(note.title);
    setContent(
      note.content.startsWith(richPrefix)
        ? plainText(note.content)
        : note.content,
    );
    setError("");
  };
  const start = () => {
    setSelected({
      id: "new",
      project_id: null,
      title: "",
      content: "",
      document_type: "quick_note",
      status: "inbox",
      tags: [],
      archived: false,
      exclude_from_ai: false,
      review_at: null,
      version: 1,
      created_at: "",
      updated_at: "",
    });
    setTitle("");
    setContent("");
  };
  const save = async () => {
    if (!selected || !title.trim() || selected.content.startsWith(richPrefix))
      return;
    setSaving(true);
    setError("");
    try {
      if (selected.id === "new")
        await request<Note>("/knowledge/documents", {
          method: "POST",
          body: JSON.stringify({
            title: title.trim(),
            content,
            document_type: "quick_note",
            status: "inbox",
            tags: [],
            exclude_from_ai: false,
          }),
        });
      else
        await request<Note>(`/knowledge/documents/${selected.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            title: title.trim(),
            content,
            expected_version: selected.version,
          }),
        });
      setSelected(null);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSaving(false);
    }
  };
  if (selected) {
    const designed = selected.content.startsWith(richPrefix);
    return (
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.bg }}
        contentContainerStyle={local.editor}
        keyboardShouldPersistTaps="handled"
      >
        <View style={local.editorTop}>
          <SecondaryButton
            compact
            label="Back"
            onPress={() => setSelected(null)}
            colors={colors}
          />
          <Text style={[local.saveState, { color: colors.muted }]}>
            {designed
              ? "Designed note · read only"
              : saving
                ? "Saving…"
                : "Mobile note"}
          </Text>
          <PrimaryButton
            compact
            label="Save"
            onPress={() => void save()}
            colors={colors}
            disabled={saving || designed || !title.trim()}
          />
        </View>
        <TextInput
          accessibilityLabel="Note title"
          value={title}
          onChangeText={setTitle}
          editable={!designed}
          placeholder="Title"
          placeholderTextColor={colors.muted}
          style={[local.noteTitle, { color: colors.text }]}
        />
        <TextInput
          accessibilityLabel="Note content"
          value={content}
          onChangeText={setContent}
          editable={!designed}
          multiline
          placeholder="Start writing…"
          placeholderTextColor={colors.muted}
          textAlignVertical="top"
          style={[local.noteBody, { color: colors.text }]}
        />
        {designed && (
          <Text
            style={[
              local.designedNotice,
              { color: colors.muted, borderColor: colors.line },
            ]}
          >
            This note contains desktop magazine layout. It is protected from
            accidental formatting loss on mobile.
          </Text>
        )}
        <ErrorNotice message={error} colors={colors} />
      </ScrollView>
    );
  }
  return (
    <Screen colors={colors} refreshing={loading}>
      <View style={local.titleWithAction}>
        <View>
          <Eyebrow colors={colors}>Notes and documents</Eyebrow>
          <Text style={[local.pageTitle, { color: colors.text }]}>Writing</Text>
        </View>
        <PrimaryButton
          compact
          label="New note"
          onPress={start}
          colors={colors}
        />
      </View>
      <ErrorNotice message={error} colors={colors} />
      {notes.length ? (
        <Card colors={colors} style={local.listCard}>
          {notes.map((note, index) => (
            <Pressable
              key={note.id}
              onPress={() => open(note)}
              style={[
                local.noteRow,
                index > 0 && { borderTopColor: colors.line, borderTopWidth: 1 },
              ]}
            >
              <Text
                numberOfLines={1}
                style={[local.rowTitle, { color: colors.text }]}
              >
                {note.title || "Untitled"}
              </Text>
              <Text
                numberOfLines={2}
                style={[local.noteExcerpt, { color: colors.muted }]}
              >
                {plainText(note.content) || "Empty note"}
              </Text>
            </Pressable>
          ))}
        </Card>
      ) : (
        <EmptyState
          title="A quiet page"
          detail="Capture a thought, meeting note or first draft."
          colors={colors}
        />
      )}
    </Screen>
  );
}

export function MoreScreen({
  colors,
  user,
  workspace,
  workspaces,
  onWorkspace,
  onWorkspacesChanged,
  onLogout,
}: {
  colors: Palette;
  user: User;
  workspace: Workspace | null;
  workspaces: Workspace[];
  onWorkspace: (workspace: Workspace) => void;
  onWorkspacesChanged: () => Promise<void>;
  onLogout: () => void;
}) {
  const [sheet, setSheet] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<OperationsKey | null>(null);
  const colorsList = ["#3B5948", "#5F6F62", "#7A6B50", "#6A7564", "#46584C"];
  const [color, setColor] = useState(colorsList[0] ?? "#3B5948");
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const created = await request<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), color }),
      });
      await onWorkspacesChanged();
      onWorkspace(created);
      setName("");
      setSheet(false);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  if (operation)
    return (
      <OperationsScreen
        kind={operation}
        colors={colors}
        ownerId={user.id}
        onBack={() => setOperation(null)}
        onLogout={onLogout}
      />
    );
  const operationItems: Array<{
    key: OperationsKey;
    title: string;
    detail: string;
    icon: IconName;
  }> = [
    {
      key: "search",
      title: "Search",
      detail: "Find work across your Orin workspace",
      icon: "search",
    },
    {
      key: "memories",
      title: "Memories",
      detail: "Manage context Orin can recall",
      icon: "memory",
    },
    {
      key: "focus",
      title: "Focus",
      detail: "Start and control deep-work sessions",
      icon: "focus",
    },
    {
      key: "routines",
      title: "Routines",
      detail: "Daily practice and check-ins",
      icon: "routine",
    },
    {
      key: "opportunities",
      title: "Opportunities and risks",
      detail: "Evaluate choices and responses",
      icon: "opportunity",
    },
    {
      key: "calendar",
      title: "Calendar",
      detail: "Events and the next 30 days",
      icon: "calendar",
    },
    {
      key: "notifications",
      title: "Notifications",
      detail: "Reminders and follow-up controls",
      icon: "notification",
    },
    {
      key: "approvals",
      title: "Approvals",
      detail: "Review permission-gated actions",
      icon: "approval",
    },
    {
      key: "activity",
      title: "Activity",
      detail: "System and execution audit trail",
      icon: "activity",
    },
    {
      key: "settings",
      title: "Preferences",
      detail: "Appearance and AI behavior",
      icon: "settings",
    },
    {
      key: "account",
      title: "Account security",
      detail: "Password and signed-in devices",
      icon: "account",
    },
  ];
  const operationGroup = (keys: OperationsKey[]) => (
    <Card colors={colors} style={local.listCard}>
      {operationItems.filter(item => keys.includes(item.key)).map((item, index) => (
        <Pressable key={item.key} onPress={() => setOperation(item.key)} style={[local.operationRow, index > 0 && { borderTopColor: colors.line, borderTopWidth: 1 }]}>
          <View style={local.operationMark}><Icon name={item.icon} size={20} color={colors.accent} /></View>
          <View style={local.rowCopy}><Text style={[local.workspaceName, { color: colors.text }]}>{item.title}</Text><Text style={[local.rowMeta, { color: colors.muted }]}>{item.detail}</Text></View>
          <Icon name="right" size={17} color={colors.muted} />
        </Pressable>
      ))}
    </Card>
  );
  return (
    <Screen colors={colors}>
      <View>
        <Eyebrow colors={colors}>Account and workspaces</Eyebrow>
        <Text style={[local.pageTitle, { color: colors.text }]}>More</Text>
      </View>
      <Card colors={colors}>
        <Text style={[local.profileName, { color: colors.text }]}>
          {user.display_name}
        </Text>
        <Text style={[local.profileEmail, { color: colors.muted }]}>
          {user.email}
        </Text>
      </Card>
      <SectionTitle colors={colors}>Find and remember</SectionTitle>
      {operationGroup(["search", "memories"])}
      <SectionTitle colors={colors}>Plan and review</SectionTitle>
      {operationGroup(["focus", "routines", "opportunities", "calendar"])}
      <SectionTitle colors={colors}>Control and account</SectionTitle>
      {operationGroup(["notifications", "approvals", "activity", "settings", "account"])}
      <SectionTitle
        colors={colors}
        action={
          <SecondaryButton
            compact
            label="New"
            onPress={() => setSheet(true)}
            colors={colors}
          />
        }
      >
        Workspaces
      </SectionTitle>
      <Card colors={colors} style={local.listCard}>
        {workspaces.map((item, index) => (
          <Pressable
            key={item.id}
            onPress={() => onWorkspace(item)}
            style={[
              local.workspaceRow,
              index > 0 && { borderTopColor: colors.line, borderTopWidth: 1 },
            ]}
          >
            <View
              style={[local.workspaceDot, { backgroundColor: item.color }]}
            />
            <Text style={[local.workspaceName, { color: colors.text }]}>
              {item.name}
            </Text>
            {workspace?.id === item.id && (
              <Icon name="check" size={18} color={colors.accent} />
            )}
          </Pressable>
        ))}
      </Card>
      <SectionTitle colors={colors}>Connection</SectionTitle>
      <Card colors={colors}>
        <Text style={[local.connectionTitle, { color: colors.text }]}>
          Orin API
        </Text>
        <Text style={[local.connectionCopy, { color: colors.muted }]}>
          This app uses the same account, tasks, projects, workspaces and AI
          command service as the web application.
        </Text>
      </Card>
      <SecondaryButton label="Sign out" onPress={onLogout} colors={colors} />
      <Sheet
        visible={sheet}
        title="New workspace"
        onClose={() => setSheet(false)}
        colors={colors}
      >
        <View style={local.sheetFields}>
          <Field
            label="Workspace name"
            colors={colors}
            value={name}
            onChangeText={setName}
            autoFocus
          />
          <Text style={[local.label, { color: colors.muted }]}>Color</Text>
          <View style={local.colorRow}>
            {colorsList.map((value) => (
              <Pressable
                key={value}
                accessibilityRole="radio"
                accessibilityState={{ checked: color === value }}
                accessibilityLabel={`Color ${value}`}
                onPress={() => setColor(value)}
                style={[
                  local.colorChoice,
                  {
                    backgroundColor: value,
                    borderColor: color === value ? colors.text : "transparent",
                  },
                ]}
              />
            ))}
          </View>
          <ErrorNotice message={error} colors={colors} />
          <PrimaryButton
            label={busy ? "Creating…" : "Create workspace"}
            onPress={() => void create()}
            colors={colors}
            disabled={busy || !name.trim()}
          />
        </View>
      </Sheet>
    </Screen>
  );
}

const greeting = () => {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
};
const local = StyleSheet.create({
  auth: {
    flexGrow: 1,
    padding: 24,
    paddingTop: 70,
    paddingBottom: 40,
    justifyContent: "center",
    gap: 30,
  },
  brandMark: { flexDirection: "row", alignItems: "center", gap: 10 },
  brandDisc: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
  },
  brandGlyph: { color: "white", fontSize: 21 },
  brand: { fontSize: 28, fontWeight: "800", letterSpacing: -1.2 },
  authIntro: { gap: 9 },
  authTitle: {
    fontSize: 42,
    lineHeight: 46,
    fontWeight: "700",
    letterSpacing: -1.7,
  },
  authCopy: { fontSize: 16, lineHeight: 24, maxWidth: 420 },
  authCard: { gap: 16 },
  passwordToggle: { alignSelf: "flex-end", minHeight: 44, justifyContent: "center", marginTop: -12 },
  passwordToggleText: { fontSize: 13, fontWeight: "600" },
  switchAuth: {
    textAlign: "center",
    fontSize: 13,
    fontWeight: "600",
    paddingVertical: 6,
  },
  hero: { gap: 8, paddingTop: 8 },
  heroTitle: {
    fontSize: 32,
    lineHeight: 37,
    fontWeight: "700",
    letterSpacing: -1.2,
  },
  heroCopy: { fontSize: 15 },
  pageTitle: {
    fontSize: 34,
    lineHeight: 40,
    fontWeight: "700",
    letterSpacing: -1.3,
    marginTop: 5,
  },
  titleWithAction: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: 12,
  },
  askCard: { gap: 10 },
  askLabel: { fontSize: 11, fontWeight: "800", letterSpacing: 1.2 },
  askInput: { minHeight: 84, fontSize: 17, lineHeight: 25, padding: 0 },
  askFooter: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  askHint: { fontSize: 10, flex: 1 },
  answer: { marginTop: 10, fontSize: 15, lineHeight: 23 },
  dailyContext: { fontSize: 13, lineHeight: 20 },
  listCard: { paddingVertical: 0 },
  row: {
    minHeight: 70,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 13,
  },
  rowCopy: { flex: 1, gap: 4 },
  rowTitle: { fontSize: 15, fontWeight: "600", lineHeight: 20 },
  rowMeta: { fontSize: 11, textTransform: "capitalize" },
  taskDot: { width: 18, height: 18, borderRadius: 9, borderWidth: 2 },
  capture: { gap: 12, padding: 12 },
  captureRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  captureInput: { flex: 1, minHeight: 42, fontSize: 16 },
  filterRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  doneToggle: { flexDirection: "row", alignItems: "center", gap: 8 },
  check: {
    width: 23,
    height: 23,
    borderRadius: 12,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  checkText: { color: "white", fontSize: 13, fontWeight: "800" },
  projectTop: { flexDirection: "row", gap: 12, alignItems: "center" },
  projectListRow: { paddingVertical: 16 },
  projectGlyph: {
    width: 42,
    height: 42,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  projectName: { fontSize: 17, fontWeight: "700" },
  projectObjective: { marginTop: 14, fontSize: 13, lineHeight: 20 },
  projectDetailHeading: { flex: 1, minWidth: 0 },
  projectDetailTitle: { fontSize: 18, fontWeight: "700", marginTop: 2 },
  sheetFields: { gap: 16 },
  editor: { flexGrow: 1, padding: 20, paddingBottom: 70 },
  editorTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    marginBottom: 24,
  },
  saveState: { fontSize: 11, flex: 1, textAlign: "center" },
  noteTitle: {
    fontSize: 34,
    lineHeight: 40,
    fontWeight: "700",
    letterSpacing: -1.3,
    paddingVertical: 8,
  },
  noteBody: { minHeight: 500, fontSize: 18, lineHeight: 30, paddingTop: 18 },
  designedNotice: {
    borderTopWidth: 1,
    paddingTop: 14,
    fontSize: 12,
    lineHeight: 18,
  },
  noteRow: { paddingVertical: 16, gap: 5 },
  noteExcerpt: { fontSize: 12, lineHeight: 18 },
  profileName: { fontSize: 20, fontWeight: "700" },
  profileEmail: { marginTop: 5, fontSize: 13 },
  workspaceRow: {
    minHeight: 58,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  workspaceDot: { width: 12, height: 12, borderRadius: 6 },
  workspaceName: { flex: 1, fontSize: 15, fontWeight: "600" },
  operationRow: {
    minHeight: 68,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  operationMark: {
    width: 38,
    height: 38,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  connectionTitle: { fontSize: 15, fontWeight: "700" },
  connectionCopy: { marginTop: 7, fontSize: 12, lineHeight: 19 },
  label: { fontSize: 12, fontWeight: "600" },
  choiceWrap: { gap: 8 },
  choiceRow: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  choice: {
    minHeight: 35,
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  colorRow: { flexDirection: "row", gap: 13 },
  colorChoice: { width: 38, height: 38, borderRadius: 19, borderWidth: 3 },
});
