/** Discard project responses that finish after a newer selection or refresh. */
export function createProjectLoadGate() {
  let generation = 0;
  return {
    begin: () => ++generation,
    isCurrent: (ticket: number) => ticket === generation,
    invalidate: () => { generation += 1; },
  };
}
