import { useEffect, useState, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { errorMessage, request } from "./api";
import type { Palette } from "./theme";
import type {
  FocusSession,
  Opportunity,
  OperationsKey,
  Risk,
  Routine,
  RoutineCheckin,
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
  Sheet,
} from "./ui";

const dateKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const addDays = (date: Date, days: number) => {
  const value = new Date(date);
  value.setDate(value.getDate() + days);
  return value;
};
const timezone = () =>
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
type PlanningKey = Extract<
  OperationsKey,
  "focus" | "routines" | "opportunities"
>;

export function PlanningScreen({
  kind,
  colors,
  onBack,
}: {
  kind: PlanningKey;
  colors: Palette;
  onBack: () => void;
}) {
  return kind === "focus" ? (
    <FocusPanel colors={colors} onBack={onBack} />
  ) : kind === "routines" ? (
    <RoutinePanel colors={colors} onBack={onBack} />
  ) : (
    <OpportunityPanel colors={colors} onBack={onBack} />
  );
}

function Header({
  title,
  eyebrow,
  colors,
  onBack,
  action,
}: {
  title: string;
  eyebrow: string;
  colors: Palette;
  onBack: () => void;
  action?: ReactNode;
}) {
  return (
    <View style={styles.header}>
      <SecondaryButton compact label="Back" onPress={onBack} colors={colors} />
      <View style={styles.heading}>
        <Eyebrow colors={colors}>{eyebrow}</Eyebrow>
        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      </View>
      {action ?? <View style={{ width: 48 }} />}
    </View>
  );
}

function FocusPanel({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [items, setItems] = useState<FocusSession[]>([]);
  const [objective, setObjective] = useState("");
  const [minutes, setMinutes] = useState("25");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await request<FocusSession[]>("/focus-sessions"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      await request<FocusSession>("/focus-sessions", {
        method: "POST",
        body: JSON.stringify({
          project_id: null,
          task_id: null,
          objective: objective.trim(),
          duration_minutes: Math.max(5, Math.min(480, Number(minutes) || 25)),
        }),
      });
      setObjective("");
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const action = async (
    session: FocusSession,
    value: "pause" | "resume" | "complete" | "cancel",
  ) => {
    setBusy(true);
    setError("");
    try {
      await request(`/focus-sessions/${session.id}`, {
        method: "PATCH",
        body: JSON.stringify({ action: value }),
      });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const current = items.find(
    (item) => item.status === "active" || item.status === "paused",
  );
  return (
    <Screen colors={colors} refreshing={loading}>
      <Header
        title="Focus"
        eyebrow="DEEP WORK"
        colors={colors}
        onBack={onBack}
      />
      <ErrorNotice message={error} colors={colors} />
      {current ? (
        <Card colors={colors} style={{ backgroundColor: colors.accentSoft }}>
          <Eyebrow colors={colors}>{current.status}</Eyebrow>
          <Text style={[styles.focusObjective, { color: colors.text }]}>
            {current.objective}
          </Text>
          <Text style={[styles.copy, { color: colors.muted }]}>
            {current.duration_minutes} minutes · started{" "}
            {new Date(current.started_at).toLocaleTimeString([], {
              hour: "numeric",
              minute: "2-digit",
            })}
          </Text>
          <View style={styles.actions}>
            <SecondaryButton
              compact
              label="Cancel"
              onPress={() => void action(current, "cancel")}
              colors={colors}
              disabled={busy}
            />
            <SecondaryButton
              compact
              label={current.status === "paused" ? "Resume" : "Pause"}
              onPress={() =>
                void action(
                  current,
                  current.status === "paused" ? "resume" : "pause",
                )
              }
              colors={colors}
              disabled={busy}
            />
            <PrimaryButton
              compact
              label="Complete"
              onPress={() => void action(current, "complete")}
              colors={colors}
              disabled={busy}
            />
          </View>
        </Card>
      ) : (
        <Card colors={colors}>
          <Field
            label="Focus objective"
            colors={colors}
            value={objective}
            onChangeText={setObjective}
            placeholder="What will receive your full attention?"
          />
          <View style={styles.topGap}>
            <Field
              label="Minutes"
              colors={colors}
              value={minutes}
              onChangeText={setMinutes}
              keyboardType="number-pad"
            />
          </View>
          <View style={styles.topGap}>
            <PrimaryButton
              label={busy ? "Starting…" : "Start focus session"}
              onPress={() => void start()}
              colors={colors}
              disabled={busy || !objective.trim()}
            />
          </View>
        </Card>
      )}
      <Eyebrow colors={colors}>Recent sessions</Eyebrow>
      {items
        .filter((item) => item.id !== current?.id)
        .slice(0, 10)
        .map((item) => (
          <Card key={item.id} colors={colors}>
            <View style={styles.row}>
              <View style={styles.grow}>
                <Text style={[styles.itemTitle, { color: colors.text }]}>
                  {item.objective}
                </Text>
                <Text style={[styles.meta, { color: colors.muted }]}>
                  {item.status} · {item.duration_minutes} min
                </Text>
              </View>
              <Text style={[styles.meta, { color: colors.muted }]}>
                {new Date(item.started_at).toLocaleDateString()}
              </Text>
            </View>
          </Card>
        ))}
    </Screen>
  );
}

function RoutinePanel({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [items, setItems] = useState<Routine[]>([]);
  const [occurrences, setOccurrences] = useState<RoutineCheckin[]>([]);
  const [sheet, setSheet] = useState(false);
  const [title, setTitle] = useState("");
  const [time, setTime] = useState("08:00");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const start = dateKey(new Date());
      const end = dateKey(addDays(new Date(), 7));
      const [routines, checks] = await Promise.all([
        request<Routine[]>("/calendar/routines"),
        request<RoutineCheckin[]>(
          `/calendar/routine-occurrences?start=${start}&end=${end}&timezone=${encodeURIComponent(timezone())}`,
        ),
      ]);
      setItems(routines);
      setOccurrences(checks);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      await request<Routine>("/calendar/routines", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          timezone: timezone(),
          weekdays: [0, 1, 2, 3, 4, 5, 6],
          start_date: dateKey(new Date()),
          end_date: null,
          time_of_day: time,
          duration_minutes: 30,
          minimum_minutes: 5,
          cue: "At the scheduled time",
          steps: "Begin the routine",
          minimum_action: "Do five minutes",
          reward: "Mark the progress",
          reminder_minutes: 10,
          paused: false,
        }),
      });
      setTitle("");
      setSheet(false);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const checkin = async (
    item: RoutineCheckin,
    status: "done" | "minimum" | "skipped",
  ) => {
    setBusy(true);
    try {
      await request(
        `/calendar/routines/${item.routine_id}/checkins/${item.day}`,
        { method: "PUT", body: JSON.stringify({ status }) },
      );
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const today = dateKey(new Date());
  const todayItems = occurrences.filter((item) => item.day === today);
  return (
    <Screen colors={colors} refreshing={loading}>
      <Header
        title="Routines"
        eyebrow="CONSISTENCY"
        colors={colors}
        onBack={onBack}
        action={
          <PrimaryButton
            compact
            label="New"
            onPress={() => setSheet(true)}
            colors={colors}
          />
        }
      />
      <ErrorNotice message={error} colors={colors} />
      <Eyebrow colors={colors}>Today</Eyebrow>
      {todayItems.length ? (
        todayItems.map((item) => (
          <Card key={`${item.routine_id}:${item.day}`} colors={colors}>
            <Text style={[styles.itemTitle, { color: colors.text }]}>
              {item.title}
            </Text>
            <Text style={[styles.copy, { color: colors.muted }]}>
              {new Date(item.start_at).toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit",
              })}{" "}
              · {item.duration_minutes} min · {item.status}
            </Text>
            <View style={styles.actions}>
              <SecondaryButton
                compact
                label="Skip"
                onPress={() => void checkin(item, "skipped")}
                colors={colors}
                disabled={busy}
              />
              <SecondaryButton
                compact
                label="Minimum"
                onPress={() => void checkin(item, "minimum")}
                colors={colors}
                disabled={busy}
              />
              <PrimaryButton
                compact
                label="Done"
                onPress={() => void checkin(item, "done")}
                colors={colors}
                disabled={busy}
              />
            </View>
          </Card>
        ))
      ) : (
        <EmptyState
          title="No routine today"
          detail="Create a routine to make steady progress visible."
          colors={colors}
        />
      )}
      <Eyebrow colors={colors}>All routines</Eyebrow>
      {items.map((item) => (
        <Card key={item.id} colors={colors}>
          <View style={styles.row}>
            <View style={styles.grow}>
              <Text style={[styles.itemTitle, { color: colors.text }]}>
                {item.title}
              </Text>
              <Text style={[styles.meta, { color: colors.muted }]}>
                {item.time_of_day} · {item.duration_minutes} min ·{" "}
                {item.paused ? "paused" : "active"}
              </Text>
            </View>
          </View>
        </Card>
      ))}
      <Sheet
        visible={sheet}
        title="New routine"
        onClose={() => setSheet(false)}
        colors={colors}
      >
        <View style={styles.fields}>
          <Field
            label="Routine name"
            colors={colors}
            value={title}
            onChangeText={setTitle}
            autoFocus
          />
          <Field
            label="Time (HH:MM)"
            colors={colors}
            value={time}
            onChangeText={setTime}
          />
          <ErrorNotice message={error} colors={colors} />
          <PrimaryButton
            label={busy ? "Creating…" : "Create daily routine"}
            onPress={() => void create()}
            colors={colors}
            disabled={busy || !title.trim() || !/^\d{2}:\d{2}$/.test(time)}
          />
        </View>
      </Sheet>
    </Screen>
  );
}

function OpportunityPanel({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [mode, setMode] = useState<"opportunities" | "risks">("opportunities");
  const [sheet, setSheet] = useState(false);
  const [title, setTitle] = useState("");
  const [detail, setDetail] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextOpportunities, nextRisks] = await Promise.all([
        request<Opportunity[]>("/opportunities"),
        request<Risk[]>("/risks"),
      ]);
      setOpportunities(nextOpportunities);
      setRisks(nextRisks);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      if (mode === "opportunities")
        await request<Opportunity>("/opportunities", {
          method: "POST",
          body: JSON.stringify({
            title: title.trim(),
            project_id: null,
            task_id: null,
            category: "other",
            stage: "inbox",
            description: detail.trim(),
            source_url: "",
            contact: "",
            next_action: nextAction.trim(),
            decision_notes: "",
            deadline: null,
            review_on: null,
            value: 3,
            fit: 3,
            effort: 3,
          }),
        });
      else
        await request<Risk>("/risks", {
          method: "POST",
          body: JSON.stringify({
            title: title.trim(),
            opportunity_id: null,
            project_id: null,
            likelihood: 3,
            impact: 3,
            status: "open",
            response: "reduce",
            trigger: "",
            mitigation: detail.trim(),
            review_on: null,
          }),
        });
      setTitle("");
      setDetail("");
      setNextAction("");
      setSheet(false);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const makeTask = async (item: Opportunity) => {
    setBusy(true);
    setError("");
    try {
      await request(`/opportunities/${item.id}/next-task`, { method: "POST" });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen colors={colors} refreshing={loading}>
      <Header
        title="Opportunities"
        eyebrow="DECISIONS"
        colors={colors}
        onBack={onBack}
        action={
          <PrimaryButton
            compact
            label="New"
            onPress={() => setSheet(true)}
            colors={colors}
          />
        }
      />
      <View style={styles.segment}>
        <Pressable
          onPress={() => setMode("opportunities")}
          style={[
            styles.segmentButton,
            {
              backgroundColor:
                mode === "opportunities" ? colors.accentSoft : colors.surface,
            },
          ]}
        >
          <Text
            style={{
              color: mode === "opportunities" ? colors.accent : colors.muted,
            }}
          >
            Opportunities
          </Text>
        </Pressable>
        <Pressable
          onPress={() => setMode("risks")}
          style={[
            styles.segmentButton,
            {
              backgroundColor:
                mode === "risks" ? colors.accentSoft : colors.surface,
            },
          ]}
        >
          <Text
            style={{ color: mode === "risks" ? colors.accent : colors.muted }}
          >
            Risks
          </Text>
        </Pressable>
      </View>
      <ErrorNotice message={error} colors={colors} />
      {mode === "opportunities"
        ? opportunities.map((item) => (
            <Card key={item.id} colors={colors}>
              <View style={styles.row}>
                <View style={styles.grow}>
                  <Eyebrow colors={colors}>
                    {item.category} · {item.stage}
                  </Eyebrow>
                  <Text style={[styles.itemTitle, { color: colors.text }]}>
                    {item.title}
                  </Text>
                </View>
                <Text style={[styles.score, { color: colors.accent }]}>
                  {item.fit}/5 fit
                </Text>
              </View>
              {item.description ? (
                <Text style={[styles.copy, { color: colors.muted }]}>
                  {item.description}
                </Text>
              ) : null}
              {item.next_action ? (
                <View style={styles.nextAction}>
                  <Text style={[styles.copy, { color: colors.text }]}>
                    Next: {item.next_action}
                  </Text>
                  <PrimaryButton
                    compact
                    label={item.task_id ? "Task linked" : "Make task"}
                    onPress={() => void makeTask(item)}
                    colors={colors}
                    disabled={busy || Boolean(item.task_id)}
                  />
                </View>
              ) : null}
            </Card>
          ))
        : risks.map((item) => (
            <Card key={item.id} colors={colors}>
              <Eyebrow colors={colors}>
                {item.status} · {item.response}
              </Eyebrow>
              <Text style={[styles.itemTitle, { color: colors.text }]}>
                {item.title}
              </Text>
              <Text style={[styles.score, { color: colors.danger }]}>
                Risk score {item.likelihood * item.impact}/25
              </Text>
              {item.mitigation ? (
                <Text style={[styles.copy, { color: colors.muted }]}>
                  Response: {item.mitigation}
                </Text>
              ) : null}
            </Card>
          ))}
      {(mode === "opportunities" ? opportunities : risks).length === 0 && (
        <EmptyState
          title={mode === "opportunities" ? "No opportunities" : "No risks"}
          detail="Capture it here when something deserves a deliberate decision."
          colors={colors}
        />
      )}
      <Sheet
        visible={sheet}
        title={mode === "opportunities" ? "New opportunity" : "New risk"}
        onClose={() => setSheet(false)}
        colors={colors}
      >
        <View style={styles.fields}>
          <Field
            label="Title"
            colors={colors}
            value={title}
            onChangeText={setTitle}
            autoFocus
          />
          <Field
            label={mode === "opportunities" ? "Description" : "Mitigation"}
            colors={colors}
            value={detail}
            onChangeText={setDetail}
            multiline
          />
          {mode === "opportunities" && (
            <Field
              label="Next action"
              colors={colors}
              value={nextAction}
              onChangeText={setNextAction}
            />
          )}
          <ErrorNotice message={error} colors={colors} />
          <PrimaryButton
            label={
              busy
                ? "Saving…"
                : mode === "opportunities"
                  ? "Create opportunity"
                  : "Create risk"
            }
            onPress={() => void create()}
            colors={colors}
            disabled={busy || !title.trim()}
          />
        </View>
      </Sheet>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "flex-end", gap: 12 },
  heading: { flex: 1, gap: 3 },
  title: {
    fontSize: 31,
    lineHeight: 35,
    fontWeight: "700",
    letterSpacing: -1.1,
  },
  focusObjective: {
    fontSize: 24,
    lineHeight: 30,
    fontWeight: "700",
    marginTop: 8,
  },
  copy: { fontSize: 13, lineHeight: 20, marginTop: 8 },
  meta: { fontSize: 11, marginTop: 3, textTransform: "capitalize" },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "flex-end",
    gap: 8,
    marginTop: 16,
  },
  topGap: { marginTop: 14 },
  fields: { gap: 16 },
  itemTitle: { fontSize: 17, lineHeight: 22, fontWeight: "700", marginTop: 4 },
  row: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  grow: { flex: 1 },
  segment: { flexDirection: "row", gap: 8 },
  segmentButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  score: { fontSize: 12, fontWeight: "700", marginTop: 8 },
  nextAction: { marginTop: 12, gap: 10 },
});
