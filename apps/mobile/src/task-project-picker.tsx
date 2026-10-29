import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import type { Palette } from "./theme";
import type { Project } from "./types";
import { ErrorNotice, Field, SecondaryButton } from "./ui";
import { mobileProjectLabel, searchMobileProjects } from "./task-projects";

export function TaskProjectPicker({
  projects,
  selectedId,
  onSelect,
  loading,
  error,
  onRetry,
  colors,
}: {
  projects: Project[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  loading: boolean;
  error: string;
  onRetry: () => void;
  colors: Palette;
}) {
  const [expanded, setExpanded] = useState(false);
  const [search, setSearch] = useState("");
  const { choices, total } = searchMobileProjects(projects, search);
  const selectedLabel = mobileProjectLabel(projects, selectedId);

  const choose = (id: string | null) => {
    onSelect(id);
    setSearch("");
    setExpanded(false);
  };

  const choice = (id: string | null, name: string) => (
    <Pressable
      key={id ?? "no-project"}
      accessibilityRole="radio"
      accessibilityState={{ checked: selectedId === id }}
      accessibilityLabel={name}
      onPress={() => choose(id)}
      style={{
        minHeight: 46,
        paddingHorizontal: 12,
        paddingVertical: 12,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottomWidth: 1,
        borderColor: colors.line,
      }}
    >
      <Text numberOfLines={1} style={{ color: colors.text, fontSize: 14, flex: 1 }}>{name}</Text>
      {selectedId === id && <Text style={{ color: colors.accent, fontWeight: "600" }}>Selected</Text>}
    </Pressable>
  );

  return (
    <View style={{ gap: 8 }}>
      <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "600" }}>Project</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Choose project. ${selectedLabel}`}
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((value) => !value)}
        style={{
          minHeight: 48,
          borderWidth: 1,
          borderRadius: 10,
          borderColor: colors.line,
          backgroundColor: colors.surface,
          paddingHorizontal: 14,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <Text numberOfLines={1} style={{ color: colors.text, flex: 1, fontSize: 14 }}>{selectedLabel}</Text>
        <Text style={{ color: colors.accent, fontWeight: "600", fontSize: 12 }}>{expanded ? "Close" : "Change"}</Text>
      </Pressable>
      {error ? (
        <View style={{ gap: 8 }}>
          <ErrorNotice message={`Project choices unavailable: ${error}. Existing links are preserved.`} colors={colors} />
          <SecondaryButton compact label="Retry projects" onPress={onRetry} colors={colors} />
        </View>
      ) : null}
      {expanded ? (
        <View style={{ gap: 8 }}>
          {loading ? <Text style={{ color: colors.muted }}>Loading projects…</Text> : null}
          {!loading && !error ? (
            <>
              <Field
                label="Search projects"
                colors={colors}
                value={search}
                onChangeText={setSearch}
                placeholder="Find a project by name"
              />
              <ScrollView nestedScrollEnabled style={{ maxHeight: 230 }} keyboardShouldPersistTaps="handled">
                {choice(null, "No project")}
                {choices.map((project) => choice(project.id, project.name))}
              </ScrollView>
              {total > choices.length ? (
                <Text style={{ color: colors.muted, fontSize: 12 }}>
                  Showing {choices.length} of {total} projects. Refine the search to find another.
                </Text>
              ) : null}
              {total === 0 ? (
                <Text style={{ color: colors.muted, fontSize: 12 }}>No matching projects in this workspace.</Text>
              ) : null}
            </>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
