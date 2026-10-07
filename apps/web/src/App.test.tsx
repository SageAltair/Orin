import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("Orin foundation page", () => {
  it("communicates the product purpose and principles", () => {
    const markup = renderToStaticMarkup(<App />);
    expect(markup).toContain("Make room for");
    expect(markup).toContain("Your personal execution environment");
    expect(markup).toContain("Execution, with you in control");
  });
});
