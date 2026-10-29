import { describe, expect, it } from "vitest";
import { createProjectLoadGate } from "./projectLoadGate";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

describe("project refresh sequencing", () => {
  it("ignores a previous project response that finishes after the selected project", async () => {
    const gate = createProjectLoadGate();
    const oldRequest = deferred<string>();
    const newRequest = deferred<string>();
    const applied: string[] = [];

    const oldTicket = gate.begin();
    const oldCompletion = oldRequest.promise.then(value => {
      if (gate.isCurrent(oldTicket)) applied.push(value);
    });
    const newTicket = gate.begin();
    const newCompletion = newRequest.promise.then(value => {
      if (gate.isCurrent(newTicket)) applied.push(value);
    });

    newRequest.resolve("Project B");
    await newCompletion;
    oldRequest.resolve("Project A");
    await oldCompletion;
    expect(applied).toEqual(["Project B"]);
  });

  it("ignores a previous refresh of the same project", () => {
    const gate = createProjectLoadGate();
    const first = gate.begin();
    const second = gate.begin();
    expect(gate.isCurrent(first)).toBe(false);
    expect(gate.isCurrent(second)).toBe(true);
  });

  it("invalidates pending responses when a project is cleared or the view unmounts", () => {
    const gate = createProjectLoadGate();
    const pending = gate.begin();
    gate.invalidate();
    expect(gate.isCurrent(pending)).toBe(false);
    expect(gate.isCurrent(gate.begin())).toBe(true);
  });
});
