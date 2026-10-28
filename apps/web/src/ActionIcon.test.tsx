import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ActionIcon } from "./ActionIcon";
import { WritingStudio } from "./WritingStudio";

describe("Orin action icon system", () => {
  it.each(["add", "close", "bell", "check", "book", "idea", "network", "layers"] as const)(
    "renders the %s icon as an accessible decorative SVG",
    (name) => {
      const markup = renderToStaticMarkup(<ActionIcon name={name} size={20} />);
      expect(markup).toContain("<svg");
      expect(markup).toContain('width="20"');
      expect(markup).toContain('aria-hidden="true"');
      expect(markup).toContain("</svg>");
    },
  );

  it("renders every writing tab using Orin SVG icons", () => {
    const markup = renderToStaticMarkup(
      <WritingStudio projects={[]} userId="test-user" onOpenTask={() => undefined} />,
    );
    for (const label of ["Notes", "Idea inbox", "Connections", "Manuscript"]) {
      expect(markup).toContain(label);
    }
    expect(markup.match(/<svg/g)).toHaveLength(4);
    expect(markup).toContain('aria-label="Writing views"');
  });
});
