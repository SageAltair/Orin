import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { scheduleTaskScreenRefresh } from "./task-screen-refresh";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("mobile Tasks foreground refresh", () => {
  it("updates the clock, polls only in the foreground, refreshes on resume and cleans up", () => {
    let foreground = true;
    let resume = () => {};
    const unsubscribe = vi.fn();
    const onClock = vi.fn();
    const onRefresh = vi.fn();
    const stop = scheduleTaskScreenRefresh({
      onClock,
      onRefresh,
      isForeground: () => foreground,
      subscribeForeground: (callback) => {
        resume = callback;
        return unsubscribe;
      },
    });

    vi.advanceTimersByTime(15_000);
    expect(onClock).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();
    vi.advanceTimersByTime(45_000);
    expect(onClock).toHaveBeenCalledTimes(4);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    foreground = false;
    vi.advanceTimersByTime(60_000);
    resume();
    expect(onClock).toHaveBeenCalledTimes(4);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    foreground = true;
    resume();
    expect(onClock).toHaveBeenCalledTimes(5);
    expect(onRefresh).toHaveBeenCalledTimes(2);

    stop();
    vi.advanceTimersByTime(60_000);
    expect(onClock).toHaveBeenCalledTimes(5);
    expect(onRefresh).toHaveBeenCalledTimes(2);
    expect(unsubscribe).toHaveBeenCalledOnce();
  });
});
