import type { ColorSchemeName } from "react-native";

export type Palette = {
  bg: string;
  surface: string;
  surfaceMuted: string;
  text: string;
  muted: string;
  line: string;
  accent: string;
  accentSoft: string;
  teal: string;
  danger: string;
  shadow: string;
  statusBar: "light" | "dark";
};
export const light: Palette = {
  bg: "#FAF9F6",
  surface: "#FFFEFA",
  surfaceMuted: "#F0EFEA",
  text: "#282D28",
  muted: "#6E756B",
  line: "#E7E6DF",
  accent: "#3B5948",
  accentSoft: "#E5EADD",
  teal: "#3B806A",
  danger: "#B4473D",
  shadow: "#232D25",
  statusBar: "dark",
};
export const dark: Palette = {
  bg: "#1C211E",
  surface: "#242B26",
  surfaceMuted: "#29322B",
  text: "#E4E7DD",
  muted: "#9BA598",
  line: "#343D35",
  accent: "#C2D1B3",
  accentSoft: "#303E31",
  teal: "#9BC8B3",
  danger: "#F08A7E",
  shadow: "#000000",
  statusBar: "light",
};
export const paletteFor = (scheme: ColorSchemeName | null) =>
  scheme === "dark" ? dark : light;
