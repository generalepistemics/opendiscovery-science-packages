// What Stop may end, decided here on a fresh read of the tree, never on the
// panel's word: one job (what an agent or the terminal started, see
// findJobTops), or every job in the built-in terminal and project actions.
// The app, the OpenDiscovery Engine server, idle shells and this service are never on
// the list, whatever the request says.
import type { TreeMember } from './tree.ts';
import { findJobTops, subtreePids } from './tree.ts';

export type StopTarget =
  /** `name` is the job's process name the panel saw; a reused pid under another name is refused. */
  | { kind: 'job'; pid: number; name: string }
  | { kind: 'terminals' };

export const parseStopTarget = (value: unknown): StopTarget | null => {
  if (typeof value !== 'object' || value === null) return null;
  const kind = Reflect.get(value, 'kind');
  if (kind === 'terminals') return { kind };
  const pid = Reflect.get(value, 'pid');
  const name = Reflect.get(value, 'name');
  if (kind === 'job' && Number.isInteger(pid) && pid > 0 && typeof name === 'string' && name) return { kind, pid, name };
  return null;
};

export interface StopPlan {
  pids: number[];
  /** Stop only if one of `pids` listens on a port; the sampler checks, since ports cost a read. */
  needsPort: boolean;
}

/**
 * Pids to stop, or `null` when the target is not something Stop may touch.
 * A job goes as a whole, so a watcher in it can't start the server again.
 */
export const planStop = (
  members: ReadonlyMap<number, TreeMember>,
  commands: ReadonlyMap<number, string>,
  target: StopTarget,
): StopPlan | null => {
  const tops = findJobTops(members, commands);
  if (target.kind === 'job') {
    const member = members.get(target.pid);
    const group = tops.get(target.pid);
    if (!member || !group) return null;
    if (member.process.name.replace(/\.exe$/i, '') !== target.name.replace(/\.exe$/i, '')) return null;
    // An agent's job is stoppable only while it serves a port: OpenDiscovery Engine's own
    // provider CLIs and MCP servers are jobs too, and ending them breaks chats.
    return { pids: subtreePids(members, target.pid), needsPort: group === 'opencode' };
  }
  // Interactive shells aren't jobs, so terminal tabs survive; what they run stops.
  const pids = [...tops].filter(([, group]) => group === 'terminals').flatMap(([pid]) => subtreePids(members, pid));
  return { pids, needsPort: false };
};
