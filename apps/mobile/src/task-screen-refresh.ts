/** Keep a visible Tasks screen current without polling while the app is backgrounded. */
export function scheduleTaskScreenRefresh(options: {
  onClock: () => void;
  onRefresh: () => void;
  isForeground: () => boolean;
  subscribeForeground: (callback: () => void) => () => void;
}): () => void {
  const clock = setInterval(() => {
    if (options.isForeground()) options.onClock();
  }, 15_000);
  const poll = setInterval(() => {
    if (options.isForeground()) options.onRefresh();
  }, 60_000);
  const unsubscribe = options.subscribeForeground(() => {
    if (!options.isForeground()) return;
    options.onClock();
    options.onRefresh();
  });
  return () => {
    clearInterval(clock);
    clearInterval(poll);
    unsubscribe();
  };
}
