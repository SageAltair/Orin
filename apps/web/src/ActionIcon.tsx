import type { SVGProps } from "react";

type ActionName = "add" | "close" | "settings" | "menu" | "pin";
type ActionIconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: ActionName;
  size?: number;
};

/** Orin's own compact action glyphs, with a shared stroke and optical size. */
export function ActionIcon({ name, size = 18, ...props }: ActionIconProps) {
  const glyphs = {
    add: <path d="M12 5v14M5 12h14" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    pin: <><path d="M9 3.5h6l-.8 6 2.8 3v1.5H7v-1.5l2.8-3z"/><path d="M12 14v7"/></>,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    settings: <><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="2" fill="var(--surface, white)" /><circle cx="15" cy="17" r="2" fill="var(--surface, white)" /></>,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {glyphs[name]}
    </svg>
  );
}
