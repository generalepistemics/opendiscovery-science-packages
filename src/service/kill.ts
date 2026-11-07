// Ends processes politely, then firmly: SIGTERM (taskkill without /F on
// Windows), and whatever is still alive after GRACE_MS gets killed.
import { execFile } from 'node:child_process';

const GRACE_MS = 3_000;
const POLL_MS = 150;

const isAlive = (pid: number): boolean => {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    // EPERM: it exists but isn't ours to signal, which we treat as alive.
    return error instanceof Error && 'code' in error && error.code === 'EPERM';
  }
};

const taskkill = (pids: readonly number[], force: boolean): Promise<void> => new Promise((resolve) => {
  const args = [...(force ? ['/F'] : []), '/T', ...pids.flatMap((pid) => ['/PID', String(pid)])];
  // taskkill exits non-zero when some pid is already gone; that is the goal, not a failure.
  execFile('taskkill', args, { windowsHide: true, timeout: 10_000 }, () => resolve());
});

const signal = (pids: readonly number[], name: NodeJS.Signals): void => {
  for (const pid of pids) {
    try {
      process.kill(pid, name);
    } catch {
      // already gone
    }
  }
};

/** Resolves with the pids that were still alive after the forced stop. */
export const stopProcesses = async (pids: readonly number[]): Promise<number[]> => {
  if (pids.length === 0) return [];
  if (process.platform === 'win32') await taskkill(pids, false);
  else signal(pids, 'SIGTERM');
  const deadline = Date.now() + GRACE_MS;
  while (Date.now() < deadline && pids.some(isAlive)) await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  const left = pids.filter(isAlive);
  if (left.length === 0) return [];
  if (process.platform === 'win32') await taskkill(left, true);
  else signal(left, 'SIGKILL');
  await new Promise((resolve) => setTimeout(resolve, POLL_MS * 2));
  return left.filter(isAlive);
};
