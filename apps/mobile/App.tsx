import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  AppState,
  BackHandler,
  Platform,
  Pressable,
  StatusBar as NativeStatusBar,
  StyleSheet,
  Text,
  useColorScheme,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import {
  errorMessage,
  getActiveWorkspaceId,
  logout,
  request,
  restoreSession,
  setActiveWorkspace,
} from "./src/api";
import {
  AuthScreen,
  HomeScreen,
  MoreScreen,
  NotesScreen,
  ProjectsScreen,
  TasksScreen,
} from "./src/screens";
import { paletteFor } from "./src/theme";
import type { TabKey, User, Workspace } from "./src/types";
import { ErrorNotice, Sheet, TabBar } from "./src/ui";
import { Icon } from "./src/icons";
import { reconcileLocalReminderAccount, reminderOwnerForSession } from "./src/native-reminders";
import { refreshDeviceReminders } from "./src/device-reminder-sync";

export default function App() {
  const scheme = useColorScheme();
  const colors = useMemo(() => paletteFor(scheme), [scheme]);
  const [booting, setBooting] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [tab, setTab] = useState<TabKey>("home");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [workspacePicker, setWorkspacePicker] = useState(false);
  const [error, setError] = useState("");
  const [dataRevision, setDataRevision] = useState(0);
  const [reminderRevision, setReminderRevision] = useState(0);

  const loadWorkspaces = async () => {
    try {
      const rows = await request<Workspace[]>("/workspaces");
      setWorkspaces(rows);
      const preferred =
        rows.find((item) => item.id === workspace?.id) ??
        rows.find((item) => item.id === getActiveWorkspaceId()) ??
        rows[0] ??
        null;
      if (preferred) await setActiveWorkspace(preferred.id);
      setWorkspace(preferred);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  useEffect(() => {
    void restoreSession()
      .then(async (restored) => {
        setUser(restored);
        if (restored) await loadWorkspaces();
      })
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    // A failed offline session restore is not an explicit logout. Clearing
    // schedules here would silently discard already-opted-in future alerts
    // whenever Orin starts without network access. signOut() clears them.
    const owner = reminderOwnerForSession(booting, user?.id ?? null);
    if (!owner) return;
    void reconcileLocalReminderAccount(owner).catch(() => {
      Alert.alert("Device reminders", "Could not reconcile reminders from a previous account. Check Android notification settings.");
    });
  }, [booting, user?.id]);

  useEffect(() => {
    if (!user || !workspace) return;
    let current = true;
    const refresh = () => {
      void refreshDeviceReminders(user.id, () => current).catch(() => {
        // Preserve previously scheduled alerts on transient network failure.
        // The Notifications screen provides an explicit retry and error message.
      });
    };
    refresh();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") refresh();
    });
    return () => {
      current = false;
      subscription.remove();
    };
  }, [user?.id, workspace?.id, reminderRevision]);

  useEffect(() => {
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      if (!user || tab === "home") return false;
      setTab("home");
      return true;
    });
    return () => subscription.remove();
  }, [tab, user]);

  const chooseWorkspace = async (next: Workspace) => {
    await setActiveWorkspace(next.id);
    setWorkspace(next);
    setWorkspacePicker(false);
    setError("");
    setDataRevision((value) => value + 1);
  };
  const signOut = async () => {
    try {
      await logout();
    } catch {
      // The API may be unreachable, but local sign-out must still complete.
      Alert.alert(
        "Signed out on this device",
        "Orin could not confirm server-side session revocation. Revoke this device from account security when connected.",
      );
    } finally {
      try {
        await reconcileLocalReminderAccount(null);
      } catch {
        Alert.alert("Device reminders", "Could not cancel device reminders. Disable Orin notifications in Android settings until this is resolved.");
      }
      setUser(null);
      setWorkspaces([]);
      setWorkspace(null);
      setTab("home");
    }
  };

  const systemInset =
    Platform.OS === "android" ? (NativeStatusBar.currentHeight ?? 0) : 0;
  if (booting)
    return (
      <View
        style={[
          styles.boot,
          { backgroundColor: colors.bg, paddingTop: systemInset },
        ]}
      >
        <Icon name="brand" color={colors.accent} size={42} />
        <ActivityIndicator color={colors.accent} />
        <StatusBar style={colors.statusBar} />
      </View>
    );
  if (!user)
    return (
      <View
        style={{ flex: 1, backgroundColor: colors.bg, paddingTop: systemInset }}
      >
        <AuthScreen
          colors={colors}
          onAuthenticated={async (next) => {
            setUser(next);
            await loadWorkspaces();
          }}
        />
        <StatusBar style={colors.statusBar} />
      </View>
    );

  return (
    <View
      style={[
        styles.safe,
        { backgroundColor: colors.bg, paddingTop: systemInset },
      ]}
    >
      <StatusBar style={colors.statusBar} />
      <View
        style={[
          styles.topbar,
          { backgroundColor: colors.surface, borderBottomColor: colors.line },
        ]}
      >
        <View style={styles.brand}>
          <Icon name="brand" color={colors.accent} size={27} />
          <Text style={[styles.brandText, { color: colors.text }]}>orin</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Switch workspace"
          onPress={() => setWorkspacePicker(true)}
          style={({ pressed }) => [
            styles.workspaceButton,
            { backgroundColor: pressed ? colors.surfaceMuted : "transparent" },
          ]}
        >
          <View
            style={[
              styles.workspaceDot,
              { backgroundColor: workspace?.color ?? colors.accent },
            ]}
          />
          <Text
            numberOfLines={1}
            style={[styles.workspaceText, { color: colors.text }]}
          >
            {workspace?.name ?? "Workspace"}
          </Text>
          <Icon name="down" color={colors.muted} size={16} />
        </Pressable>
      </View>
      {error ? (
        <View style={styles.globalError}>
          <ErrorNotice message={error} colors={colors} />
        </View>
      ) : null}
      <View
        style={styles.content}
        key={`${workspace?.id ?? "none"}-${dataRevision}`}
      >
        {tab === "home" && (
          <HomeScreen
            colors={colors}
            user={user}
            workspace={workspace}
            active
            onDataChanged={() => {
              setDataRevision((value) => value + 1);
              setReminderRevision((value) => value + 1);
            }}
          />
        )}
        {tab === "tasks" && (
          <TasksScreen
            colors={colors}
            workspace={workspace}
            active
            onTasksChanged={() => setReminderRevision((value) => value + 1)}
          />
        )}
        {tab === "projects" && (
          <ProjectsScreen colors={colors} workspace={workspace} active />
        )}
        {tab === "notes" && <NotesScreen colors={colors} active />}
        {tab === "more" && (
          <MoreScreen
            colors={colors}
            user={user}
            workspace={workspace}
            workspaces={workspaces}
            onWorkspace={(next) => void chooseWorkspace(next)}
            onWorkspacesChanged={loadWorkspaces}
            onLogout={() => void signOut()}
          />
        )}
      </View>
      <TabBar selected={tab} onSelect={setTab} colors={colors} />
      <Sheet
        visible={workspacePicker}
        title="Choose workspace"
        onClose={() => setWorkspacePicker(false)}
        colors={colors}
      >
        <View>
          {workspaces.map((item, index) => (
            <Pressable
              key={item.id}
              onPress={() => void chooseWorkspace(item)}
              style={[
                styles.workspaceRow,
                index > 0 && { borderTopColor: colors.line, borderTopWidth: 1 },
              ]}
            >
              <View
                style={[
                  styles.workspaceDotLarge,
                  { backgroundColor: item.color },
                ]}
              />
              <View style={styles.workspaceCopy}>
                <Text style={[styles.workspaceName, { color: colors.text }]}>
                  {item.name}
                </Text>
                <Text style={[styles.workspaceMeta, { color: colors.muted }]}>
                  {item.id === workspace?.id
                    ? "Current workspace"
                    : "Open workspace"}
                </Text>
              </View>
              {item.id === workspace?.id && (
                <Icon name="check" size={18} color={colors.accent} />
              )}
            </Pressable>
          ))}
        </View>
      </Sheet>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  boot: { flex: 1, alignItems: "center", justifyContent: "center", gap: 22 },
  logo: {
    width: 62,
    height: 62,
    borderRadius: 31,
    alignItems: "center",
    justifyContent: "center",
  },
  logoText: { color: "white", fontSize: 38 },
  topbar: {
    minHeight: 57,
    paddingHorizontal: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
  },
  brand: { flexDirection: "row", alignItems: "center", gap: 8 },
  logoSmall: {
    width: 27,
    height: 27,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  logoSmallText: { color: "white", fontSize: 17 },
  brandText: { fontSize: 22, fontWeight: "800", letterSpacing: -0.8 },
  workspaceButton: {
    maxWidth: "57%",
    minHeight: 38,
    borderRadius: 11,
    paddingHorizontal: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  workspaceDot: { width: 9, height: 9, borderRadius: 5 },
  workspaceText: { flexShrink: 1, fontSize: 12, fontWeight: "600" },
  globalError: { padding: 10 },
  content: { flex: 1 },
  workspaceRow: {
    minHeight: 70,
    flexDirection: "row",
    alignItems: "center",
    gap: 13,
  },
  workspaceDotLarge: { width: 15, height: 15, borderRadius: 8 },
  workspaceCopy: { flex: 1, gap: 3 },
  workspaceName: { fontSize: 16, fontWeight: "600" },
  workspaceMeta: { fontSize: 11 },
});
