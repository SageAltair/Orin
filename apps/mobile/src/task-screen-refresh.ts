/** Keep a visible Tasks screen current without polling while the app is backgrounded. */
export function scheduleTaskScreenRefresh(options: {
  onClock: () => void;
  onRefresh: () => void;
  isForeground: () => boolean;
  subscribeAppState: (callback: (state: string) => void) => () => void;
}): () => void {
  const clock = setInterval(() => {
    if (options.isForeground()) options.onClock();
  }, 15_000);
  const poll = setInterval(() => {
    if (options.isForeground()) options.onRefresh();
  }, 60_000);
  const unsubscribe = options.subscribeAppState((state) => {
    // The event's new state is authoritative; currentState can lag the event.
    if (state !== "active") return;
    options.onClock();
    options.onRefresh();
  });
  return () => {
    clearInterval(clock);
    clearInterval(poll);
    unsubscribe();
  };
}
