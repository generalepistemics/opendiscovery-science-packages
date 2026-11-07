// Pure readers for what each OS prints. No I/O here, so every format has a test.

/** One process as the OS lists it, before we know whether it is ours. */
export interface RawProcess {
  pid: number;
  ppid: number;
  name: string;
  /** Resident memory in bytes. */
  memory: number;
  /** User plus system CPU time since the process started, in seconds. */
  cpuSeconds: number;
  /** Start time in ms since the epoch, where the OS reuses parent pids (Windows). */
  startedAt?: number;
  /** Controlling terminal (`ttys004`, a Linux tty number); absent without one or on Windows. */
  tty?: string;
}

const toInt = (value: string | undefined): number => {
  const parsed = Number.parseInt(value ?? '', 10);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
};

const basename = (path: string): string => {
  const trimmed = path.trim();
  const slash = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
  return slash >= 0 ? trimmed.slice(slash + 1) : trimmed;
};

/** `ps` cputime: `ss.cc`, `mm:ss.cc`, `hh:mm:ss`, or `dd-hh:mm:ss`. */
export const parseCpuTime = (value: string): number => {
  const [daysPart, clock] = value.includes('-') ? value.split('-', 2) : ['0', value];
  const parts = (clock ?? '').split(':').map(Number);
  if (parts.some((part) => !Number.isFinite(part))) return Number.NaN;
  let seconds = 0;
  for (const part of parts) seconds = seconds * 60 + part;
  return Number(daysPart) * 86_400 + seconds;
};

/** `ps -A -o pid=,ppid=,rss=,cputime=,tty=,comm=` on macOS. `comm` is last because it may hold spaces. */
export const parsePsList = (stdout: string): RawProcess[] => {
  const rows: RawProcess[] = [];
  for (const line of stdout.split('\n')) {
    const match = /^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(.+?)\s*$/.exec(line);
    if (!match) continue;
    const pid = toInt(match[1]);
    const ppid = toInt(match[2]);
    const rssKb = toInt(match[3]);
    const cpuSeconds = parseCpuTime(match[4] ?? '');
    if (!Number.isFinite(pid) || !Number.isFinite(ppid)) continue;
    const tty = match[5] ?? '??';
    rows.push({
      pid,
      ppid,
      name: basename(match[6] ?? ''),
      memory: Number.isFinite(rssKb) ? rssKb * 1024 : 0,
      cpuSeconds: Number.isFinite(cpuSeconds) ? cpuSeconds : 0,
      ...(tty === '??' || tty === '-' ? {} : { tty }),
    });
  }
  return rows;
};

/** `ps -o pid=,command= -p ...`: the full command line per pid. */
export const parsePsCommands = (stdout: string): Map<number, string> => {
  const commands = new Map<number, string>();
  for (const line of stdout.split('\n')) {
    const match = /^\s*(\d+)\s+(.*?)\s*$/.exec(line);
    if (match) commands.set(toInt(match[1]), match[2] ?? '');
  }
  return commands;
};

/**
 * `vm_stat` on macOS, counted the way Activity Monitor's "Memory Used" is:
 * app memory (anonymous minus purgeable), wired, and compressed.
 */
export const parseVmStatUsed = (stdout: string): number | null => {
  const pageSize = toInt(/page size of (\d+) bytes/.exec(stdout)?.[1]);
  const pages = (label: string): number => {
    const match = new RegExp(`^${label}:\\s+(\\d+)`, 'm').exec(stdout);
    return match ? toInt(match[1]) : Number.NaN;
  };
  const anonymous = pages('Anonymous pages');
  const purgeable = pages('Pages purgeable');
  const wired = pages('Pages wired down');
  const compressed = pages('Pages occupied by compressor');
  const values = [pageSize, anonymous, wired, compressed];
  if (values.some((value) => !Number.isFinite(value))) return null;
  const app = Math.max(0, anonymous - (Number.isFinite(purgeable) ? purgeable : 0));
  return (app + wired + compressed) * pageSize;
};

/** `/proc/meminfo`: used is total minus MemAvailable, as `free` reports it. */
export const parseMeminfoUsed = (content: string): number | null => {
  const read = (label: string): number => toInt(new RegExp(`^${label}:\\s+(\\d+) kB`, 'm').exec(content)?.[1]) * 1024;
  const total = read('MemTotal');
  const available = read('MemAvailable');
  return Number.isFinite(total) && Number.isFinite(available) ? Math.max(0, total - available) : null;
};

/**
 * `/proc/<pid>/stat`. The name sits in parentheses and may itself contain
 * spaces and parentheses, so fields are counted from the last `)`.
 */
export const parseLinuxStat = (content: string, ticksPerSecond: number, pageSize: number): RawProcess | null => {
  const open = content.indexOf('(');
  const close = content.lastIndexOf(')');
  if (open < 0 || close < open) return null;
  const pid = toInt(content.slice(0, open));
  const fields = content.slice(close + 2).split(' ');
  // After the name: state(0) ppid(1) pgrp(2) session(3) tty_nr(4) ... utime(11) stime(12) ... rss(21).
  const ppid = toInt(fields[1]);
  const tty = fields[4];
  const utime = toInt(fields[11]);
  const stime = toInt(fields[12]);
  const rss = toInt(fields[21]);
  if (!Number.isFinite(pid) || !Number.isFinite(ppid)) return null;
  return {
    pid,
    ppid,
    name: content.slice(open + 1, close),
    memory: Number.isFinite(rss) ? rss * pageSize : 0,
    cpuSeconds: Number.isFinite(utime + stime) ? (utime + stime) / ticksPerSecond : 0,
    ...(tty && tty !== '0' ? { tty } : {}),
  };
};

/** `/proc/<pid>/cmdline`: arguments separated by NUL. */
export const parseCmdline = (content: string): string => content.split('\0').filter(Boolean).join(' ');

/** `/proc/net/tcp` and `tcp6`: listening sockets as inode → port. */
export const parseProcNetTcp = (content: string): Map<string, number> => {
  const listening = new Map<string, number>();
  for (const line of content.split('\n').slice(1)) {
    const fields = line.trim().split(/\s+/);
    // sl local_address rem_address st tx:rx tr:when retrnsmt uid timeout inode
    if (fields[3] !== '0A') continue;
    const port = Number.parseInt(fields[1]?.split(':')[1] ?? '', 16);
    const inode = fields[9];
    if (inode && inode !== '0' && Number.isFinite(port)) listening.set(inode, port);
  }
  return listening;
};

/** `socket:[12345]` from a `/proc/<pid>/fd/*` link. */
export const socketInode = (link: string): string | null => /^socket:\[(\d+)\]$/.exec(link)?.[1] ?? null;

const addPort = (ports: Map<number, number[]>, pid: number, port: number): void => {
  if (!Number.isFinite(pid) || !Number.isFinite(port) || port <= 0) return;
  const list = ports.get(pid) ?? [];
  if (!list.includes(port)) list.push(port);
  ports.set(pid, list);
};

const portOf = (address: string): number => toInt(address.slice(address.lastIndexOf(':') + 1));

/** `lsof -nP -a -p <pids> -iTCP -sTCP:LISTEN -Fpn`: `p<pid>` then `n<address>:<port>` lines. */
export const parseLsofListen = (stdout: string): Map<number, number[]> => {
  const ports = new Map<number, number[]>();
  let pid = Number.NaN;
  for (const line of stdout.split('\n')) {
    if (line.startsWith('p')) pid = toInt(line.slice(1));
    else if (line.startsWith('n')) addPort(ports, pid, portOf(line.slice(1)));
  }
  return ports;
};

/**
 * `netstat -ano -p TCP` and `-p TCPv6` on Windows. The state column is
 * translated on non-English systems, so a listener is recognised by its
 * empty remote end (`0.0.0.0:0` or `[::]:0`) instead of the word LISTENING.
 */
export const parseNetstatListen = (stdout: string): Map<number, number[]> => {
  const ports = new Map<number, number[]>();
  for (const line of stdout.split(/\r?\n/)) {
    const fields = line.trim().split(/\s+/);
    if (fields[0] !== 'TCP' || fields.length < 5) continue;
    const remote = fields[2] ?? '';
    if (remote !== '0.0.0.0:0' && remote !== '[::]:0') continue;
    addPort(ports, toInt(fields[fields.length - 1]), portOf(fields[1] ?? ''));
  }
  return ports;
};

/**
 * One block from the Windows PowerShell helper: tab-separated
 * pid, ppid, working set bytes, CPU time in 100 ns units, start time in
 * ms since the epoch (empty when Windows doesn't say), name.
 */
export const parseWindowsList = (stdout: string): RawProcess[] => {
  const rows: RawProcess[] = [];
  for (const line of stdout.split(/\r?\n/)) {
    const [pid, ppid, memory, cpu, started, ...name] = line.split('\t');
    const parsedPid = toInt(pid);
    const parsedPpid = toInt(ppid);
    if (!Number.isFinite(parsedPid) || !Number.isFinite(parsedPpid)) continue;
    const bytes = Number(memory);
    const ticks = Number(cpu);
    const startedAt = Number.parseInt(started ?? '', 10);
    rows.push({
      pid: parsedPid,
      ppid: parsedPpid,
      name: name.join('\t').trim(),
      memory: Number.isFinite(bytes) ? bytes : 0,
      cpuSeconds: Number.isFinite(ticks) ? ticks / 1e7 : 0,
      ...(Number.isFinite(startedAt) ? { startedAt } : {}),
    });
  }
  return rows;
};

/** The helper's command-line answer: tab-separated pid and command line. */
export const parseWindowsCommands = (stdout: string): Map<number, string> => {
  const commands = new Map<number, string>();
  for (const line of stdout.split(/\r?\n/)) {
    const tab = line.indexOf('\t');
    if (tab < 0) continue;
    const pid = toInt(line.slice(0, tab));
    if (Number.isFinite(pid)) commands.set(pid, line.slice(tab + 1).trim());
  }
  return commands;
};
