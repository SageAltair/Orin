import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";
import type { Palette } from "./theme";
import type { TabKey } from "./types";
import { Icon, type IconName } from "./icons";

export const Screen = ({
  children,
  colors,
  refreshing = false,
}: {
  children: ReactNode;
  colors: Palette;
  refreshing?: boolean;
}) => (
  <ScrollView
    style={{ flex: 1, backgroundColor: colors.bg }}
    contentContainerStyle={styles.screen}
    keyboardShouldPersistTaps="handled"
  >
    {refreshing && (
      <ActivityIndicator color={colors.accent} style={styles.loader} />
    )}
    {children}
  </ScrollView>
);

export const Eyebrow = ({
  children,
  colors,
}: {
  children: ReactNode;
  colors: Palette;
}) => <Text style={[styles.eyebrow, { color: colors.muted }]}>{children}</Text>;

export const SectionTitle = ({
  children,
  action,
  colors,
}: {
  children: ReactNode;
  action?: ReactNode;
  colors: Palette;
}) => (
  <View style={styles.sectionTitle}>
    <Text style={[styles.sectionHeading, { color: colors.text }]}>
      {children}
    </Text>
    {action}
  </View>
);

export const Card = ({
  children,
  colors,
  style,
}: {
  children: ReactNode;
  colors: Palette;
  style?: StyleProp<ViewStyle>;
}) => (
  <View
    style={[
      styles.card,
      {
        backgroundColor: colors.surface,
        borderColor: colors.line,
        shadowColor: colors.shadow,
      },
      style,
    ]}
  >
    {children}
  </View>
);

export const PrimaryButton = ({
  label,
  onPress,
  colors,
  disabled = false,
  compact = false,
}: {
  label: string;
  onPress: () => void;
  colors: Palette;
  disabled?: boolean;
  compact?: boolean;
}) => (
  <Pressable
    accessibilityRole="button"
    disabled={disabled}
    onPress={onPress}
    style={({ pressed }) => [
      styles.primary,
      compact && styles.compactButton,
      {
        backgroundColor: colors.accent,
        opacity: disabled ? 0.45 : pressed ? 0.82 : 1,
      },
    ]}
  >
    <Text style={styles.primaryText}>{label}</Text>
  </Pressable>
);

export const SecondaryButton = ({
  label,
  onPress,
  colors,
  disabled = false,
  compact = false,
}: {
  label: string;
  onPress: () => void;
  colors: Palette;
  disabled?: boolean;
  compact?: boolean;
}) => (
  <Pressable
    accessibilityRole="button"
    disabled={disabled}
    onPress={onPress}
    style={({ pressed }) => [
      styles.secondary,
      compact && styles.compactButton,
      {
        borderColor: colors.line,
        backgroundColor: pressed ? colors.surfaceMuted : colors.surface,
        opacity: disabled ? 0.45 : 1,
      },
    ]}
  >
    <Text style={[styles.secondaryText, { color: colors.text }]}>{label}</Text>
  </Pressable>
);

export const Field = ({
  label,
  colors,
  multiline,
  ...props
}: TextInputProps & { label: string; colors: Palette }) => (
  <View style={styles.fieldWrap}>
    <Text style={[styles.label, { color: colors.muted }]}>{label}</Text>
    <TextInput
      accessibilityLabel={label}
      placeholderTextColor={colors.muted}
      multiline={multiline}
      textAlignVertical={multiline ? "top" : "center"}
      style={[
        styles.field,
        multiline && styles.multiline,
        {
          color: colors.text,
          borderColor: colors.line,
          backgroundColor: colors.surface,
        },
      ]}
      {...props}
    />
  </View>
);

export const ErrorNotice = ({
  message,
  colors,
}: {
  message: string;
  colors: Palette;
}) =>
  message ? (
    <View
      accessibilityRole="alert"
      style={[styles.notice, { backgroundColor: `${colors.danger}18` }]}
    >
      <Text style={{ color: colors.danger }}>{message}</Text>
    </View>
  ) : null;

export const EmptyState = ({
  title,
  detail,
  colors,
}: {
  title: string;
  detail: string;
  colors: Palette;
}) => (
  <View style={styles.empty}>
    <Text style={[styles.emptyTitle, { color: colors.text }]}>{title}</Text>
    <Text style={[styles.emptyDetail, { color: colors.muted }]}>{detail}</Text>
  </View>
);

export const Sheet = ({
  visible,
  title,
  onClose,
  children,
  colors,
}: {
  visible: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  colors: Palette;
}) => (
  <Modal
    visible={visible}
    transparent
    animationType="slide"
    onRequestClose={onClose}
  >
    <Pressable style={styles.scrim} onPress={onClose}>
      <Pressable
        style={[
          styles.sheet,
          { backgroundColor: colors.bg, borderColor: colors.line },
        ]}
        onPress={() => undefined}
      >
        <View style={styles.sheetHeader}>
          <Text style={[styles.sheetTitle, { color: colors.text }]}>
            {title}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close"
            onPress={onClose}
            style={styles.iconButton}
          >
            <Icon name="close" size={20} color={colors.muted} />
          </Pressable>
        </View>
        {children}
      </Pressable>
    </Pressable>
  </Modal>
);

const tabs: Array<{ key: TabKey; label: string; icon: IconName }> = [
  { key: "home", label: "Home", icon: "home" },
  { key: "tasks", label: "Tasks", icon: "tasks" },
  { key: "projects", label: "Projects", icon: "projects" },
  { key: "notes", label: "Writing", icon: "writing" },
  { key: "more", label: "More", icon: "more" },
];
export const TabBar = ({
  selected,
  onSelect,
  colors,
}: {
  selected: TabKey;
  onSelect: (tab: TabKey) => void;
  colors: Palette;
}) => (
  <View
    accessibilityRole="tablist"
    style={[
      styles.tabBar,
      { backgroundColor: colors.surface, borderTopColor: colors.line },
    ]}
  >
    {tabs.map((tab) => {
      const active = selected === tab.key;
      return (
        <Pressable
          key={tab.key}
          accessibilityRole="tab"
          accessibilityState={{ selected: active }}
          accessibilityLabel={tab.label}
          onPress={() => onSelect(tab.key)}
          style={styles.tab}
        >
          <View style={styles.tabIconContainer}>
            <Icon
              name={tab.icon}
              size={21}
              strokeWidth={active ? 2.1 : 1.7}
              color={active ? colors.accent : colors.muted}
            />
          </View>
          <Text
            style={[
              styles.tabText,
              {
                color: active ? colors.accent : colors.muted,
                fontWeight: active ? "700" : "500",
              },
            ]}
          >
            {tab.label}
          </Text>
        </Pressable>
      );
    })}
  </View>
);

export const styles = StyleSheet.create({
  screen: { paddingHorizontal: 20, paddingTop: 24, paddingBottom: 48, gap: 20 },
  loader: { marginVertical: 4 },
  eyebrow: { fontSize: 12, fontWeight: "600", letterSpacing: 0.35 },
  sectionTitle: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 4,
  },
  sectionHeading: { fontSize: 20, fontWeight: "700", letterSpacing: -0.4 },
  card: {
    borderWidth: 1,
    borderRadius: 9,
    padding: 17,
    shadowOpacity: 0,
    elevation: 0,
  },
  primary: {
    minHeight: 48,
    borderRadius: 7,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 18,
  },
  primaryText: { color: "#FFFFFF", fontSize: 15, fontWeight: "700" },
  secondary: {
    minHeight: 46,
    borderRadius: 7,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  secondaryText: { fontSize: 14, fontWeight: "600" },
  compactButton: { minHeight: 38, borderRadius: 7, paddingHorizontal: 12 },
  fieldWrap: { gap: 7 },
  label: { fontSize: 12, fontWeight: "600" },
  field: {
    minHeight: 48,
    borderWidth: 1,
    borderRadius: 7,
    paddingHorizontal: 13,
    fontSize: 16,
  },
  multiline: { minHeight: 132, paddingTop: 13 },
  notice: { borderRadius: 12, padding: 13 },
  empty: { paddingVertical: 44, alignItems: "center", gap: 7 },
  emptyTitle: { fontSize: 17, fontWeight: "700" },
  emptyDetail: { maxWidth: 280, textAlign: "center", lineHeight: 20 },
  scrim: { flex: 1, justifyContent: "flex-end", backgroundColor: "#07110B88" },
  sheet: {
    maxHeight: "88%",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    borderWidth: 1,
    padding: 20,
    paddingBottom: 32,
  },
  sheetHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 20,
  },
  sheetTitle: { fontSize: 22, fontWeight: "600" },
  iconButton: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    marginRight: -10,
  },
  tabBar: {
    flexDirection: "row",
    borderTopWidth: 1,
    paddingTop: 7,
    paddingBottom: 9,
    paddingHorizontal: 6,
  },
  tab: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
    minHeight: 54,
  },
  tabIconContainer: {
    width: 32,
    height: 28,
    alignItems: "center",
    justifyContent: "center",
  },
  tabText: { fontSize: 10, letterSpacing: 0.1, fontWeight: "500" },
});
