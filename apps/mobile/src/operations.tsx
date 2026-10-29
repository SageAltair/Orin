import { useEffect, useState, type ReactNode } from "react";
import { Pressable, StyleSheet, Switch, Text, View } from "react-native";
import { errorMessage, request } from "./api";
import { getLocalReminderEnabled, setLocalReminderEnabled, syncLocalReminders } from "./native-reminders";
import type {
  Activity,
  Approval,
  CalendarEvent,
  NotificationPolicy,
  OperationsKey,
  Reminder,
} from "./types";
import type { Palette } from "./theme";
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
import { PlanningScreen } from "./planning";
import { InformationScreen } from "./information";

const dateKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const addDays = (date: Date, amount: number) => {
  const next = new Date(date);
  next.setDate(next.getDate() + amount);
  return next;
};
const zone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const dateTime = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

export function OperationsScreen({
  kind,
  colors,
  onBack,
  onLogout,
  ownerId,
}: {
  kind: OperationsKey;
  colors: Palette;
  onBack: () => void;
  onLogout?: () => void;
  ownerId: string;
}) {
  if (kind === "focus" || kind === "routines" || kind === "opportunities")
    return <PlanningScreen kind={kind} colors={colors} onBack={onBack} />;
  if (
    kind === "search" ||
    kind === "memories" ||
    kind === "settings" ||
    kind === "account"
  )
    return (
      <InformationScreen
        kind={kind}
        colors={colors}
        onBack={onBack}
        onLogout={onLogout}
      />
    );
  return (
    <View style={{ flex: 1 }}>
      {kind === "calendar" ? (
        <CalendarOperation colors={colors} onBack={onBack} />
      ) : kind === "notifications" ? (
        <NotificationOperation colors={colors} onBack={onBack} ownerId={ownerId} />
      ) : kind === "approvals" ? (
        <ApprovalOperation colors={colors} onBack={onBack} />
      ) : (
        <ActivityOperation colors={colors} onBack={onBack} />
      )}
    </View>
  );
}

function OperationHeader({
  eyebrow,
  title,
  colors,
  onBack,
  action,
}: {
  eyebrow: string;
  title: string;
  colors: Palette;
  onBack: () => void;
  action?: ReactNode;
}) {
  return (
    <View style={styles.header}>
      <SecondaryButton compact label="Back" onPress={onBack} colors={colors} />
      <View style={styles.headerCopy}>
        <Eyebrow colors={colors}>{eyebrow}</Eyebrow>
        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      </View>
      {action ?? <View style={styles.actionSpace} />}
    </View>
  );
}

function CalendarOperation({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [items, setItems] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sheet, setSheet] = useState(false);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(dateKey(new Date()));
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({
        start: dateKey(new Date()),
        end: dateKey(addDays(new Date(), 30)),
        timezone: zone(),
      });
      setItems(await request<CalendarEvent[]>(`/calendar/events?${query}`));
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
      await request<CalendarEvent>("/calendar/events", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          description: null,
          project_id: null,
          is_all_day: true,
          start_date: date,
          end_date: date,
          start_at: null,
          end_at: null,
          timezone: zone(),
          reminder_minutes: null,
        }),
      });
      setSheet(false);
      setTitle("");
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (id: string) => {
    try {
      await request<void>(`/calendar/events/${id}`, { method: "DELETE" });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };
  return (
    <Screen colors={colors} refreshing={loading}>
      <OperationHeader
        eyebrow="NEXT 30 DAYS"
        title="Calendar"
        colors={colors}
        onBack={onBack}
        action={
          <PrimaryButton
            compact
            label="New event"
            onPress={() => setSheet(true)}
            colors={colors}
          />
        }
      />
      <ErrorNotice message={error} colors={colors} />
      {items.length ? (
        items.map((item) => (
          <Card key={item.id} colors={colors}>
            <View style={styles.itemTop}>
              <View style={styles.itemCopy}>
                <Text style={[styles.itemTitle, { color: colors.text }]}>
                  {item.title}
                </Text>
                <Text style={[styles.meta, { color: colors.muted }]}>
                  {item.is_all_day
                    ? `${item.start_date} · All day`
                    : item.start_at
                      ? dateTime(item.start_at)
                      : "Unscheduled"}
                </Text>
              </View>
              <SecondaryButton
                compact
                label="Delete"
                onPress={() => void remove(item.id)}
                colors={colors}
              />
            </View>
            {item.description ? (
              <Text style={[styles.body, { color: colors.muted }]}>
                {item.description}
              </Text>
            ) : null}
          </Card>
        ))
      ) : (
        <EmptyState
          title="Nothing scheduled"
          detail="Add an event to shape the month ahead."
          colors={colors}
        />
      )}
      <Sheet
        visible={sheet}
        title="New calendar event"
        onClose={() => setSheet(false)}
        colors={colors}
      >
        <View style={styles.fields}>
          <Field
            label="Event title"
            colors={colors}
            value={title}
            onChangeText={setTitle}
            autoFocus
          />
          <Field
            label="Date (YYYY-MM-DD)"
            colors={colors}
            value={date}
            onChangeText={setDate}
            autoCapitalize="none"
          />
          <ErrorNotice message={error} colors={colors} />
          <PrimaryButton
            label={busy ? "Saving…" : "Save event"}
            onPress={() => void create()}
            colors={colors}
            disabled={
              busy || !title.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(date)
            }
          />
        </View>
      </Sheet>
    </Screen>
  );
}

function NotificationOperation({
  colors,
  onBack,
  ownerId,
}: {
  colors: Palette;
  onBack: () => void;
  ownerId: string;
}) {
  const [items, setItems] = useState<Reminder[]>([]);
  const [policy, setPolicy] = useState<NotificationPolicy | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deviceEnabled, setDeviceEnabled] = useState(false);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [next, prefs] = await Promise.all([
        request<Reminder[]>("/notifications"),
        request<NotificationPolicy>("/notifications/preferences"),
      ]);
      setItems(next);
      setPolicy(prefs);
      const enabled = await getLocalReminderEnabled(ownerId);
      setDeviceEnabled(enabled);
      if (enabled) await syncLocalReminders(ownerId, next, prefs);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const act = async (id: string, action: "acknowledge" | "snooze") => {
    try {
      await request(`/notifications/${id}/action`, {
        method: "POST",
        body: JSON.stringify({ action, minutes: 15 }),
      });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };
  const changeDeviceReminders = async (enabled: boolean) => {
    if (!policy) return;
    setDeviceBusy(true);
    setError("");
    try {
      const accepted = await setLocalReminderEnabled(ownerId, enabled, items, policy);
      setDeviceEnabled(accepted);
      if (enabled && !accepted) {
        setError("Android notifications are blocked for Orin. Enable app and reminder-channel notifications in system settings, then try again.");
      }
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setDeviceBusy(false);
    }
  };
  const save = async () => {
    if (!policy) return;
    setSaving(true);
    setError("");
    try {
      const updated = await request<NotificationPolicy>("/notifications/preferences", {
        method: "PUT",
        body: JSON.stringify(policy),
      });
      setPolicy(updated);
      if (deviceEnabled) await syncLocalReminders(ownerId, items, updated);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Screen colors={colors} refreshing={loading}>
      <OperationHeader
        eyebrow="FOLLOW-UP"
        title="Notifications"
        colors={colors}
        onBack={onBack}
      />
      <ErrorNotice message={error} colors={colors} />
      {policy && (
        <Card colors={colors}>
          <Text style={[styles.body, { color: colors.muted }]}>
            Orin can schedule known upcoming reminders on this device when you
            explicitly enable device alerts. New server reminders will not arrive
            while the app is closed until push delivery is implemented. Android
            may delay alerts; silent mode and Do Not Disturb still apply.
            Future focus sessions cannot be checked while Orin is closed.
          </Text>
          <Toggle
            label={deviceBusy ? "Updating device alerts..." : "Device reminders (opt in)"}
            disabled={deviceBusy}
            value={deviceEnabled}
            onChange={(enabled) => void changeDeviceReminders(enabled)}
            colors={colors}
          />
          <Toggle
            label="Automatic notifications"
            value={policy.enabled}
            onChange={(value) => setPolicy({ ...policy, enabled: value })}
            colors={colors}
          />
          <Toggle
            label="Persistent follow-up"
            value={policy.persistent}
            onChange={(value) => setPolicy({ ...policy, persistent: value })}
            colors={colors}
          />
          <Toggle
            label="Respect focus sessions"
            value={policy.respect_focus}
            onChange={(value) => setPolicy({ ...policy, respect_focus: value })}
            colors={colors}
          />
          <PrimaryButton
            compact
            label={saving ? "Saving…" : "Save preferences"}
            onPress={() => void save()}
            colors={colors}
            disabled={saving}
          />
        </Card>
      )}
      {items.length ? (
        items.map((item) => (
          <Card key={item.id} colors={colors}>
            <Eyebrow colors={colors}>{item.category}</Eyebrow>
            <Text style={[styles.itemTitle, { color: colors.text }]}>
              {item.title}
            </Text>
            <Text style={[styles.body, { color: colors.muted }]}>
              {item.message}
            </Text>
            <Text style={[styles.meta, { color: colors.muted }]}>
              {dateTime(item.due_at)}
              {item.read_at ? " · Acknowledged" : ""}
            </Text>
            {!item.read_at && (
              <View style={styles.actions}>
                <SecondaryButton
                  compact
                  label="Snooze 15m"
                  onPress={() => void act(item.id, "snooze")}
                  colors={colors}
                />
                <PrimaryButton
                  compact
                  label="Acknowledge"
                  onPress={() => void act(item.id, "acknowledge")}
                  colors={colors}
                />
              </View>
            )}
          </Card>
        ))
      ) : (
        <EmptyState
          title="No reminders"
          detail="New reminders and follow-up prompts will appear here."
          colors={colors}
        />
      )}
    </Screen>
  );
}

function Toggle({
  label,
  value,
  onChange,
  colors,
  disabled = false,
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  colors: Palette;
  disabled?: boolean;
}) {
  return (
    <View style={styles.toggle}>
      <Text style={[styles.toggleLabel, { color: colors.text }]}>{label}</Text>
      <Switch
        value={value}
        disabled={disabled}
        onValueChange={onChange}
        trackColor={{ true: colors.accent }}
      />
    </View>
  );
}

function ApprovalOperation({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [items, setItems] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await request<Approval[]>("/approvals"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const decide = async (id: string, approved: boolean) => {
    setBusyId(id);
    setError("");
    try {
      await request(`/approvals/${id}/decision`, {
        method: "POST",
        body: JSON.stringify({
          approved,
          note: approved
            ? "Approved from Orin Android"
            : "Denied from Orin Android",
        }),
      });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusyId("");
    }
  };
  const sorted = [...items].sort(
    (a, b) => Number(b.status === "pending") - Number(a.status === "pending"),
  );
  return (
    <Screen colors={colors} refreshing={loading}>
      <OperationHeader
        eyebrow="CONTROL"
        title="Approvals"
        colors={colors}
        onBack={onBack}
      />
      <ErrorNotice message={error} colors={colors} />
      {sorted.length ? (
        sorted.map((item) => (
          <Card key={item.id} colors={colors}>
            <View style={styles.itemTop}>
              <View style={styles.itemCopy}>
                <Eyebrow colors={colors}>{item.risk_level} RISK</Eyebrow>
                <Text style={[styles.itemTitle, { color: colors.text }]}>
                  {item.action?.replaceAll("_", " ") || "Requested action"}
                </Text>
              </View>
              <Text
                style={[
                  styles.status,
                  {
                    color:
                      item.status === "pending" ? colors.accent : colors.muted,
                  },
                ]}
              >
                {item.status}
              </Text>
            </View>
            {item.reason ? (
              <Text style={[styles.body, { color: colors.muted }]}>
                {item.reason}
              </Text>
            ) : null}
            <Text
              numberOfLines={4}
              style={[
                styles.parameters,
                { color: colors.muted, backgroundColor: colors.surfaceMuted },
              ]}
            >
              {JSON.stringify(item.parameters, null, 2)}
            </Text>
            {item.status === "pending" && (
              <View style={styles.actions}>
                <SecondaryButton
                  compact
                  label="Deny"
                  onPress={() => void decide(item.id, false)}
                  colors={colors}
                  disabled={busyId === item.id}
                />
                <PrimaryButton
                  compact
                  label={busyId === item.id ? "Working…" : "Approve"}
                  onPress={() => void decide(item.id, true)}
                  colors={colors}
                  disabled={busyId === item.id}
                />
              </View>
            )}
          </Card>
        ))
      ) : (
        <EmptyState
          title="No approvals"
          detail="Actions that require your consent will appear here."
          colors={colors}
        />
      )}
    </Screen>
  );
}

function ActivityOperation({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [items, setItems] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await request<Activity[]>("/activity?limit=100"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  return (
    <Screen colors={colors} refreshing={loading}>
      <OperationHeader
        eyebrow="AUDIT TRAIL"
        title="Activity"
        colors={colors}
        onBack={onBack}
      />
      <ErrorNotice message={error} colors={colors} />
      {items.length ? (
        <Card colors={colors} style={{ paddingVertical: 0 }}>
          {items.map((item, index) => (
            <View
              key={item.id}
              style={[
                styles.activity,
                index > 0 && { borderTopWidth: 1, borderTopColor: colors.line },
              ]}
            >
              <View
                style={[
                  styles.activityDot,
                  {
                    backgroundColor:
                      item.severity === "error"
                        ? colors.danger
                        : item.result_status === "succeeded"
                          ? colors.teal
                          : colors.accent,
                  },
                ]}
              />
              <View style={styles.itemCopy}>
                <Text style={[styles.activityTitle, { color: colors.text }]}>
                  {item.summary}
                </Text>
                <Text style={[styles.meta, { color: colors.muted }]}>
                  {item.source} · {item.result_status} ·{" "}
                  {dateTime(item.created_at)}
                </Text>
              </View>
            </View>
          ))}
        </Card>
      ) : (
        <EmptyState
          title="No recent activity"
          detail="Completed operations and lifecycle changes will appear here."
          colors={colors}
        />
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "flex-end", gap: 12 },
  headerCopy: { flex: 1, gap: 3 },
  title: {
    fontSize: 31,
    lineHeight: 35,
    fontWeight: "700",
    letterSpacing: -1.1,
  },
  actionSpace: { width: 54 },
  fields: { gap: 16 },
  itemTop: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  itemCopy: { flex: 1, gap: 4 },
  itemTitle: { fontSize: 17, fontWeight: "700", lineHeight: 22, marginTop: 4 },
  body: { fontSize: 13, lineHeight: 20, marginTop: 10 },
  meta: { fontSize: 11, marginTop: 6 },
  actions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 8,
    marginTop: 15,
  },
  toggle: {
    minHeight: 54,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  toggleLabel: { fontSize: 14, fontWeight: "600" },
  status: { fontSize: 11, fontWeight: "700", textTransform: "uppercase" },
  parameters: {
    marginTop: 13,
    padding: 12,
    borderRadius: 10,
    fontSize: 11,
    lineHeight: 16,
  },
  activity: {
    minHeight: 68,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 12,
  },
  activityDot: { width: 9, height: 9, borderRadius: 5 },
  activityTitle: { fontSize: 14, fontWeight: "600", lineHeight: 19 },
});
