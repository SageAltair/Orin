import { useEffect, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { errorMessage, request } from "./api";
import type {
  AuthSession,
  Memory,
  OperationsKey,
  SearchResult,
  UserPreferences,
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

type InformationKey = Extract<
  OperationsKey,
  "search" | "memories" | "settings" | "account"
>;

export function InformationScreen({
  kind,
  colors,
  onBack,
  onLogout,
}: {
  kind: InformationKey;
  colors: Palette;
  onBack: () => void;
  onLogout?: () => void;
}) {
  if (kind === "search")
    return <SearchScreen colors={colors} onBack={onBack} />;
  if (kind === "memories")
    return <MemoriesScreen colors={colors} onBack={onBack} />;
  if (kind === "settings")
    return <PreferencesScreen colors={colors} onBack={onBack} />;
  return <AccountScreen colors={colors} onBack={onBack} onLogout={onLogout} />;
}

function Header({
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
  action?: React.ReactNode;
}) {
  return (
    <View style={styles.header}>
      <SecondaryButton compact label="Back" onPress={onBack} colors={colors} />
      <View style={styles.headerCopy}>
        <Eyebrow colors={colors}>{eyebrow}</Eyebrow>
        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      </View>
      {action ?? <View style={{ width: 48 }} />}
    </View>
  );
}

function SearchScreen({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");
  const search = async () => {
    if (query.trim().length < 2) return;
    setBusy(true);
    setError("");
    try {
      setItems(
        await request<SearchResult[]>(
          `/search?q=${encodeURIComponent(query.trim())}&limit=50`,
        ),
      );
      setSearched(true);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen colors={colors}>
      <Header
        eyebrow="EVERYTHING IN ONE PLACE"
        title="Search"
        colors={colors}
        onBack={onBack}
      />
      <Card colors={colors} style={styles.searchBar}>
        <Field
          label="Search tasks, projects, notes and conversations"
          colors={colors}
          value={query}
          onChangeText={setQuery}
          returnKeyType="search"
          onSubmitEditing={() => void search()}
          autoFocus
        />
        <PrimaryButton
          compact
          label={busy ? "Searching…" : "Search"}
          onPress={() => void search()}
          colors={colors}
          disabled={busy || query.trim().length < 2}
        />
      </Card>
      <ErrorNotice message={error} colors={colors} />
      {items.map((item) => (
        <Card key={`${item.kind}-${item.result_id}`} colors={colors}>
          <View style={styles.resultTop}>
            <Eyebrow colors={colors}>{item.kind}</Eyebrow>
            <Text style={[styles.date, { color: colors.muted }]}>
              {new Date(item.created_at).toLocaleDateString()}
            </Text>
          </View>
          <Text style={[styles.itemTitle, { color: colors.text }]}>
            {item.title || item.text}
          </Text>
          {item.excerpt && item.excerpt !== (item.title || item.text) ? (
            <Text
              style={[styles.body, { color: colors.muted }]}
              numberOfLines={4}
            >
              {item.excerpt}
            </Text>
          ) : null}
        </Card>
      ))}
      {searched && !busy && !items.length ? (
        <EmptyState
          title="No matches"
          detail="Try a broader word or another phrase."
          colors={colors}
        />
      ) : !searched ? (
        <EmptyState
          title="Search your whole workspace"
          detail="Find a task, project, note, or prior conversation without remembering where it lives."
          colors={colors}
        />
      ) : null}
    </Screen>
  );
}

const memoryTypes = [
  "knowledge",
  "commitment",
  "decision",
  "working_style",
  "project",
  "fact",
] as const;
function MemoriesScreen({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [items, setItems] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [type, setType] = useState<string>("knowledge");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await request<Memory[]>("/memories"));
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
      await request<Memory>("/memories", {
        method: "POST",
        body: JSON.stringify({
          project_id: null,
          memory_type: type,
          title: title.trim(),
          content: content.trim(),
          source: "user",
          confidence: 1,
          evidence: [],
        }),
      });
      setTitle("");
      setContent("");
      setSheet(false);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const archive = async (item: Memory) => {
    try {
      await request<Memory>(`/memories/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ archived: true }),
      });
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };
  return (
    <Screen colors={colors} refreshing={loading}>
      <Header
        eyebrow="PERSONAL CONTEXT"
        title="Memories"
        colors={colors}
        onBack={onBack}
        action={
          <PrimaryButton
            compact
            label="Add"
            onPress={() => setSheet(true)}
            colors={colors}
          />
        }
      />
      <Text style={[styles.intro, { color: colors.muted }]}>
        Only save durable context you want Orin to recall. Secret-like content
        is rejected by the API.
      </Text>
      <ErrorNotice message={error} colors={colors} />
      {items.length ? (
        items.map((item) => (
          <Card key={item.id} colors={colors}>
            <View style={styles.resultTop}>
              <Eyebrow colors={colors}>
                {item.type.replaceAll("_", " ")}
              </Eyebrow>
              <Text style={[styles.date, { color: colors.muted }]}>
                {item.provenance ?? "explicit"}
              </Text>
            </View>
            <Text style={[styles.itemTitle, { color: colors.text }]}>
              {item.title}
            </Text>
            <Text style={[styles.body, { color: colors.muted }]}>
              {item.content}
            </Text>
            <View style={styles.actions}>
              <SecondaryButton
                compact
                label="Archive"
                onPress={() => void archive(item)}
                colors={colors}
              />
            </View>
          </Card>
        ))
      ) : (
        <EmptyState
          title="No saved memories"
          detail="Add stable preferences, decisions, commitments, or facts that should carry into future work."
          colors={colors}
        />
      )}
      <Sheet
        visible={sheet}
        title="Add memory"
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
          <Text style={[styles.label, { color: colors.muted }]}>Type</Text>
          <View style={styles.choices}>
            {memoryTypes.map((value) => (
              <Choice
                key={value}
                label={value.replaceAll("_", " ")}
                selected={type === value}
                onPress={() => setType(value)}
                colors={colors}
              />
            ))}
          </View>
          <Field
            label="What should Orin remember?"
            colors={colors}
            value={content}
            onChangeText={setContent}
            multiline
          />
          <ErrorNotice message={error} colors={colors} />
          <PrimaryButton
            label={busy ? "Saving…" : "Save memory"}
            onPress={() => void create()}
            colors={colors}
            disabled={busy || !title.trim() || !content.trim()}
          />
        </View>
      </Sheet>
    </Screen>
  );
}

function PreferencesScreen({
  colors,
  onBack,
}: {
  colors: Palette;
  onBack: () => void;
}) {
  const [prefs, setPrefs] = useState<UserPreferences | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setPrefs(await request<UserPreferences>("/users/me/preferences"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const save = async () => {
    if (!prefs) return;
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const { hidden_capabilities: _, ...payload } = prefs;
      setPrefs(
        await request<UserPreferences>("/users/me/preferences", {
          method: "PUT",
          body: JSON.stringify(payload),
        }),
      );
      setSaved(true);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Screen colors={colors} refreshing={loading}>
      <Header
        eyebrow="YOUR ORIN"
        title="Preferences"
        colors={colors}
        onBack={onBack}
      />
      <ErrorNotice message={error} colors={colors} />
      {prefs ? (
        <>
          <Card colors={colors}>
            <Setting
              title="Interface density"
              detail="Choose the spacing used across Orin."
              colors={colors}
            >
              <View style={styles.choices}>
                {(["comfortable", "compact"] as const).map((value) => (
                  <Choice
                    key={value}
                    label={value}
                    selected={prefs.density === value}
                    onPress={() => {
                      setPrefs({ ...prefs, density: value });
                      setSaved(false);
                    }}
                    colors={colors}
                  />
                ))}
              </View>
            </Setting>
            <Setting
              title="Theme preference"
              detail="Used by Orin across supported clients."
              colors={colors}
            >
              <View style={styles.choices}>
                {(["light", "dark", "system"] as const).map((value) => (
                  <Choice
                    key={value}
                    label={value}
                    selected={prefs.theme === value}
                    onPress={() => {
                      setPrefs({ ...prefs, theme: value });
                      setSaved(false);
                    }}
                    colors={colors}
                  />
                ))}
              </View>
            </Setting>
          </Card>
          <Card colors={colors}>
            <Setting
              title="AI autonomy"
              detail="Controls how often Orin asks before taking permitted action."
              colors={colors}
            >
              <View style={styles.choices}>
                {(["conservative", "balanced", "automatic"] as const).map(
                  (value) => (
                    <Choice
                      key={value}
                      label={value}
                      selected={prefs.autonomy_mode === value}
                      onPress={() => {
                        setPrefs({ ...prefs, autonomy_mode: value });
                        setSaved(false);
                      }}
                      colors={colors}
                    />
                  ),
                )}
              </View>
            </Setting>
            <Setting
              title="Proactive support"
              detail="Controls how actively Orin follows up and surfaces useful prompts."
              colors={colors}
            >
              <View style={styles.choices}>
                {(
                  ["quiet", "supportive", "proactive", "persistent"] as const
                ).map((value) => (
                  <Choice
                    key={value}
                    label={value}
                    selected={prefs.proactive_mode === value}
                    onPress={() => {
                      setPrefs({ ...prefs, proactive_mode: value });
                      setSaved(false);
                    }}
                    colors={colors}
                  />
                ))}
              </View>
            </Setting>
          </Card>
          <PrimaryButton
            label={saving ? "Saving…" : saved ? "Saved" : "Save preferences"}
            onPress={() => void save()}
            colors={colors}
            disabled={saving}
          />
        </>
      ) : !loading ? (
        <EmptyState
          title="Preferences unavailable"
          detail="Pull to refresh after the API is available."
          colors={colors}
        />
      ) : null}
    </Screen>
  );
}

function AccountScreen({
  colors,
  onBack,
  onLogout,
}: {
  colors: Palette;
  onBack: () => void;
  onLogout?: () => void;
}) {
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [passwordSheet, setPasswordSheet] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setSessions(await request<AuthSession[]>("/auth/sessions"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const revoke = (item: AuthSession) =>
    Alert.alert(
      item.current ? "Sign out this device?" : "Revoke this session?",
      item.current
        ? "You will need to sign in again."
        : "That device will no longer be able to refresh its session.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Revoke",
          style: "destructive",
          onPress: () =>
            void (async () => {
              try {
                await request<void>(`/auth/sessions/${item.id}`, {
                  method: "DELETE",
                });
                if (item.current) onLogout?.();
                else await load();
              } catch (cause) {
                setError(errorMessage(cause));
              }
            })(),
        },
      ],
    );
  const changePassword = async () => {
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await request<void>("/auth/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setPasswordSheet(false);
      Alert.alert(
        "Password changed",
        "For your security, all devices have been signed out.",
        [{ text: "Sign in again", onPress: onLogout }],
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen colors={colors} refreshing={loading}>
      <Header
        eyebrow="SECURITY"
        title="Account"
        colors={colors}
        onBack={onBack}
        action={
          <PrimaryButton
            compact
            label="Password"
            onPress={() => setPasswordSheet(true)}
            colors={colors}
          />
        }
      />
      <Text style={[styles.intro, { color: colors.muted }]}>
        Review every authenticated session. Revoke access you do not recognize.
      </Text>
      <ErrorNotice message={error} colors={colors} />
      {sessions.length ? (
        sessions.map((item) => (
          <Card key={item.id} colors={colors}>
            <View style={styles.resultTop}>
              <Eyebrow colors={colors}>
                {item.current
                  ? "THIS DEVICE"
                  : item.active
                    ? "ACTIVE"
                    : "INACTIVE"}
              </Eyebrow>
              <Text style={[styles.date, { color: colors.muted }]}>
                {new Date(item.last_used_at).toLocaleString()}
              </Text>
            </View>
            <Text style={[styles.itemTitle, { color: colors.text }]}>
              {item.current ? "Current Android session" : "Signed-in session"}
            </Text>
            <Text style={[styles.body, { color: colors.muted }]}>
              Created {new Date(item.created_at).toLocaleDateString()} · Expires{" "}
              {new Date(item.expires_at).toLocaleDateString()}
            </Text>
            {item.active ? (
              <View style={styles.actions}>
                <SecondaryButton
                  compact
                  label={item.current ? "Sign out" : "Revoke"}
                  onPress={() => revoke(item)}
                  colors={colors}
                />
              </View>
            ) : null}
          </Card>
        ))
      ) : !loading ? (
        <EmptyState
          title="No sessions found"
          detail="Your signed-in devices will appear here."
          colors={colors}
        />
      ) : null}
      <Sheet
        visible={passwordSheet}
        title="Change password"
        onClose={() => setPasswordSheet(false)}
        colors={colors}
      >
        <View style={styles.fields}>
          <Field
            label="Current password"
            colors={colors}
            value={currentPassword}
            onChangeText={setCurrentPassword}
            secureTextEntry
            autoFocus
          />
          <Field
            label="New password (15+ characters)"
            colors={colors}
            value={newPassword}
            onChangeText={setNewPassword}
            secureTextEntry
          />
          <Field
            label="Confirm new password"
            colors={colors}
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
          />
          <ErrorNotice message={error} colors={colors} />
          <PrimaryButton
            label={busy ? "Changing…" : "Change password"}
            onPress={() => void changePassword()}
            colors={colors}
            disabled={
              busy ||
              !currentPassword ||
              newPassword.length < 15 ||
              !confirmPassword
            }
          />
        </View>
      </Sheet>
    </Screen>
  );
}

function Choice({
  label,
  selected,
  onPress,
  colors,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  colors: Palette;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[
        styles.choice,
        {
          borderColor: selected ? colors.accent : colors.line,
          backgroundColor: selected ? colors.accentSoft : colors.surface,
        },
      ]}
    >
      <Text
        style={{
          color: selected ? colors.accent : colors.text,
          fontSize: 12,
          fontWeight: "700",
          textTransform: "capitalize",
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}
function Setting({
  title,
  detail,
  colors,
  children,
}: {
  title: string;
  detail: string;
  colors: Palette;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.setting}>
      <Text style={[styles.settingTitle, { color: colors.text }]}>{title}</Text>
      <Text style={[styles.settingDetail, { color: colors.muted }]}>
        {detail}
      </Text>
      {children}
    </View>
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
  searchBar: { gap: 12 },
  resultTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
  },
  date: { fontSize: 10 },
  itemTitle: { fontSize: 17, lineHeight: 23, fontWeight: "700", marginTop: 7 },
  body: { fontSize: 13, lineHeight: 20, marginTop: 8 },
  intro: { fontSize: 13, lineHeight: 20 },
  actions: { marginTop: 14, alignItems: "flex-end" },
  fields: { gap: 15 },
  label: {
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
  choice: {
    minHeight: 36,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  setting: { paddingVertical: 6, marginBottom: 16 },
  settingTitle: { fontSize: 16, fontWeight: "700" },
  settingDetail: { fontSize: 12, lineHeight: 18, marginTop: 4 },
});
