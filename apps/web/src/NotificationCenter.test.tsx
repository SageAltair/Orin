import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { NotificationCenter } from "./NotificationCenter";

describe("NotificationCenter", () => {
  it("renders an accessible reminders toggle with an explicit collapsed state", () => {
    const markup = renderToStaticMarkup(<NotificationCenter />);
    expect(markup).toContain('aria-label="Reminders"');
    expect(markup).toContain('aria-expanded="false"');
    expect(markup).toContain('aria-controls="orin-notification-panel"');
    expect(markup).toContain('class="notification-center"');
    expect(markup).toContain('aria-hidden="true"');
  });
});
