import Svg, { Circle, Line, Path, Polyline, Rect } from "react-native-svg";
export type IconName =
  | "home"
  | "tasks"
  | "projects"
  | "writing"
  | "more"
  | "close"
  | "down"
  | "right"
  | "check"
  | "brand"
  | "command"
  | "search"
  | "memory"
  | "focus"
  | "routine"
  | "opportunity"
  | "calendar"
  | "notification"
  | "approval"
  | "activity"
  | "settings"
  | "account";
export function Icon({
  name,
  size = 22,
  color = "#282D28",
  strokeWidth = 1.8,
}: {
  name: IconName;
  size?: number;
  color?: string;
  strokeWidth?: number;
}) {
  const p = {
    fill: "none",
    stroke: color,
    strokeWidth,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      accessibilityElementsHidden
    >
      {name === "brand" && (
        <>
          <Path
            {...p}
            d="M6.2 17.8C2.8 14.4 3.1 8.8 6.8 5.5c3.7-3.3 9.3-3.1 12.6.6"
          />
          <Path
            {...p}
            d="M17.8 6.2c3.4 3.4 3.1 9-.6 12.3-3.7 3.3-9.3 3.1-12.6-.6"
          />
          <Circle cx="18.7" cy="5.3" r="1.2" fill={color} />
        </>
      )}
      {name === "home" && (
        <>
          <Path
            {...p}
            d="M3.5 10.5 12 3.8l8.5 6.7M5.5 9.5v10h13v-10M9.5 19.5v-6h5v6"
          />
        </>
      )}
      {name === "tasks" && (
        <>
          <Rect {...p} x="4" y="4" width="16" height="16" rx="2" />
          <Path
            {...p}
            d="m7.5 9 1.4 1.4 2.6-3M13.5 9h3M7.5 15l1.4 1.4 2.6-3M13.5 15h3"
          />
        </>
      )}
      {name === "projects" && (
        <Path {...p} d="M3.5 7.5h6l1.7 2h10.3v9.5h-18zM3.5 7.5V5h5l1.7 2.5" />
      )}
      {name === "writing" && (
        <>
          <Path
            {...p}
            d="M5 3.5h10l4 4V20.5H5zM14.5 3.5v4h4M8.5 12h7M8.5 15.5h7"
          />
        </>
      )}
      {name === "more" && (
        <>
          <Circle {...p} cx="7" cy="7" r="1.5" />
          <Circle {...p} cx="17" cy="7" r="1.5" />
          <Circle {...p} cx="7" cy="17" r="1.5" />
          <Circle {...p} cx="17" cy="17" r="1.5" />
        </>
      )}
      {name === "close" && <Path {...p} d="m6 6 12 12M18 6 6 18" />}
      {name === "down" && <Polyline {...p} points="7 9 12 14 17 9" />}
      {name === "right" && <Polyline {...p} points="9 6 15 12 9 18" />}
      {name === "check" && <Polyline {...p} points="5 12 10 17 19 7" />}
      {name === "command" && (
        <>
          <Circle {...p} cx="12" cy="12" r="8" />
          <Path {...p} d="M12 7v10M7 12h10" />
        </>
      )}
      {name === "search" && (
        <>
          <Circle {...p} cx="10.5" cy="10.5" r="6.5" />
          <Line {...p} x1="15.5" y1="15.5" x2="21" y2="21" />
        </>
      )}
      {name === "memory" && (
        <>
          <Path
            {...p}
            d="M8 5.5a4 4 0 0 1 7.5 2A3.5 3.5 0 0 1 17 14a4 4 0 0 1-7.5 2A3.5 3.5 0 0 1 8 9.5a3 3 0 0 1 0-4zM12 6v12"
          />
        </>
      )}
      {name === "focus" && (
        <>
          <Circle {...p} cx="12" cy="12" r="8" />
          <Circle {...p} cx="12" cy="12" r="3" />
        </>
      )}
      {name === "routine" && (
        <>
          <Path {...p} d="M18 8a7 7 0 1 0 1 7" />
          <Polyline {...p} points="18 3 18 8 13 8" />
        </>
      )}
      {name === "opportunity" && (
        <>
          <Path
            {...p}
            d="M9 18h6M10 21h4M8 14c-1.3-1-2-2.7-2-4.5a6 6 0 0 1 12 0c0 1.8-.7 3.5-2 4.5-1 .8-1.5 1.6-1.5 2.5h-5C9.5 15.6 9 14.8 8 14z"
          />
        </>
      )}
      {name === "calendar" && (
        <>
          <Rect {...p} x="4" y="5.5" width="16" height="15" rx="2" />
          <Path {...p} d="M8 3.5v4M16 3.5v4M4 10h16" />
        </>
      )}
      {name === "notification" && (
        <>
          <Path
            {...p}
            d="M6 17h12l-1.5-2.5V10a4.5 4.5 0 0 0-9 0v4.5zM10 20h4"
          />
        </>
      )}
      {name === "approval" && (
        <>
          <Circle {...p} cx="12" cy="12" r="9" />
          <Polyline {...p} points="8 12 11 15 16.5 9" />
        </>
      )}
      {name === "activity" && (
        <Polyline {...p} points="3 13 7 13 9 7 13 18 16 11 21 11" />
      )}
      {name === "settings" && (
        <>
          <Circle {...p} cx="12" cy="12" r="3" />
          <Path
            {...p}
            d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"
          />
        </>
      )}
      {name === "account" && (
        <>
          <Circle {...p} cx="12" cy="8" r="4" />
          <Path {...p} d="M4.5 20c.8-4 3.3-6 7.5-6s6.7 2 7.5 6" />
        </>
      )}
    </Svg>
  );
}
