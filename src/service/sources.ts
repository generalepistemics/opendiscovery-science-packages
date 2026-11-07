// Where the numbers come from on each OS. Everything here reads; nothing
// here changes a process. Failures surface as errors for the sampler to
// turn into warnings, never as an empty list that looks like the truth.
import { execFile, spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { readdir, readFile, readlink } from 'node:fs/promises';
import os from 'node:os';

import {
  parseCmdline,
  parseLinuxStat,
  parseLsofListen,
  parseMeminfoUsed,
  parseNetstatListen,
  parseProcNetTcp,
  parsePsCommands,
  parsePsList,
  parseVmStatUsed,
  parseWindowsCommands,
  parseWindowsList,
  socketInode,
  type RawProcess,
} from './parse.ts';

export interface ProcessSource {
  list(): Promise<RawProcess[]>;
  commands(pids: readonly number[]): Promise<Map<number, string>>;
  ports(pids: readonly number[]): Promise<Map<number, number[]>>;
  /** Memory in use by the whole machine, the way the OS's own monitor counts it. */
  memoryUsed(): Promise<number>;
  close(): void;
}

const run = (file: string, args: string[], okExitCodes: number[] = [0]): Promise<string> => new Promise((resolve, reject) => {
  execFile(file, args, { timeout: 10_000, maxBuffer: 16 * 1024 * 1024, windowsHide: true }, (error, stdout) => {
    const code = error && 'code' in error && typeof error.code === 'number' ? error.code : error ? -1 : 0;
    if (!error || okExitCodes.includes(code)) resolve(stdout);
    else reject(error);
  });
});

const chunks = <T>(items: readonly T[], size: number): T[][] => {
  const result: T[][] = [];
  for (let index = 0; index < items.length; index += size) result.push(items.slice(index, index + size));
  return result;
};

const freeMemoryFallback = (): number => os.totalmem() - os.freemem();

// ----- macOS and other Unix systems with BSD ps -----

const psSource = (): ProcessSource => ({
  list: async () => parsePsList(await run('ps', ['-A', '-o', 'pid=,ppid=,rss=,cputime=,tty=,comm='])),
  commands: async (pids) => {
    const commands = new Map<number, string>();
    for (const part of chunks(pids, 200)) {
      // ps exits 1 when one of the pids ended in the meantime; the rest still print.
      for (const [pid, command] of parsePsCommands(await run('ps', ['-ww', '-o', 'pid=,command=', '-p', part.join(',')], [0, 1]))) {
        commands.set(pid, command);
      }
    }
    return commands;
  },
  ports: async (pids) => {
    const ports = new Map<number, number[]>();
    for (const part of chunks(pids, 200)) {
      // lsof exits 1 when nothing matched, which here means "no listeners".
      for (const [pid, list] of parseLsofListen(await run('lsof', ['-nP', '-a', '-p', part.join(','), '-iTCP', '-sTCP:LISTEN', '-Fpn'], [0, 1]))) {
        ports.set(pid, list);
      }
    }
    return ports;
  },
  memoryUsed: async () => {
    if (process.platform !== 'darwin') return freeMemoryFallback();
    return parseVmStatUsed(await run('vm_stat', [])) ?? freeMemoryFallback();
  },
  close: () => undefined,
});

// ----- Linux: /proc, no external commands -----

const getconf = async (name: string, fallback: number): Promise<number> => {
  try {
    const value = Number.parseInt(await run('getconf', [name]), 10);
    return Number.isFinite(value) && value > 0 ? value : fallback;
  } catch {
    return fallback;
  }
};

const linuxSource = (): ProcessSource => {
  const constants = Promise.all([getconf('CLK_TCK', 100), getconf('PAGESIZE', 4096)]);
  return {
    list: async () => {
      const [ticks, pageSize] = await constants;
      const entries = (await readdir('/proc')).filter((entry) => /^\d+$/.test(entry));
      const rows = await Promise.all(entries.map(async (pid) => {
        try {
          return parseLinuxStat(await readFile(`/proc/${pid}/stat`, 'utf8'), ticks, pageSize);
        } catch {
          return null; // ended between readdir and read
        }
      }));
      return rows.filter((row): row is RawProcess => row !== null);
    },
    commands: async (pids) => {
      const commands = new Map<number, string>();
      await Promise.all(pids.map(async (pid) => {
        try {
          commands.set(pid, parseCmdline(await readFile(`/proc/${pid}/cmdline`, 'utf8')));
        } catch {
          // ended, or not ours to read
        }
      }));
      return commands;
    },
    ports: async (pids) => {
      const listening = new Map<string, number>();
      for (const table of ['/proc/net/tcp', '/proc/net/tcp6']) {
        try {
          for (const [inode, port] of parseProcNetTcp(await readFile(table, 'utf8'))) listening.set(inode, port);
        } catch {
          // no IPv6 table on this kernel
        }
      }
      const ports = new Map<number, number[]>();
      if (listening.size === 0) return ports;
      await Promise.all(pids.map(async (pid) => {
        let fds: string[];
        try {
          fds = await readdir(`/proc/${pid}/fd`);
        } catch {
          return;
        }
        const found = new Set<number>();
        await Promise.all(fds.map(async (fd) => {
          try {
            const inode = socketInode(await readlink(`/proc/${pid}/fd/${fd}`));
            const port = inode ? listening.get(inode) : undefined;
            if (port) found.add(port);
          } catch {
            // closed in the meantime
          }
        }));
        if (found.size > 0) ports.set(pid, [...found]);
      }));
      return ports;
    },
    memoryUsed: async () => parseMeminfoUsed(await readFile('/proc/meminfo', 'utf8')) ?? freeMemoryFallback(),
    close: () => undefined,
  };
};

// ----- Windows: one long-lived PowerShell, asked over stdin -----

const END = '<<resource-monitor-end>>';

// Starting PowerShell costs about half a second, so one copy stays up while
// the panel is open and answers `list` and `commands <pid,...>` requests.
const WINDOWS_HELPER = `
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
while ($true) {
  $request = [Console]::In.ReadLine()
  if ($null -eq $request) { break }
  $lines = @()
  if ($request -eq 'list') {
    $lines = foreach ($p in Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,WorkingSetSize,KernelModeTime,UserModeTime,CreationDate,Name) {
      $started = if ($p.CreationDate) { ([DateTimeOffset]$p.CreationDate).ToUnixTimeMilliseconds() } else { '' }
      "$($p.ProcessId)\`t$($p.ParentProcessId)\`t$($p.WorkingSetSize)\`t$([uint64]$p.KernelModeTime + [uint64]$p.UserModeTime)\`t$started\`t$($p.Name)"
    }
  } elseif ($request.StartsWith('commands ')) {
    $ids = $request.Substring(9).Split(',') | Where-Object { $_ -match '^[0-9]+$' }
    if ($ids) {
      $filter = ($ids | ForEach-Object { "ProcessId=$_" }) -join ' OR '
      $lines = foreach ($p in Get-CimInstance Win32_Process -Filter $filter -Property ProcessId,CommandLine) {
        "$($p.ProcessId)\`t$($p.CommandLine -replace '[\\t\\r\\n]', ' ')"
      }
    }
  }
  [Console]::Out.WriteLine(($lines -join "\`n"))
  [Console]::Out.WriteLine('${END}')
  [Console]::Out.Flush()
}
`;

const windowsSource = (): ProcessSource => {
  let helper: ChildProcessWithoutNullStreams | null = null;
  let buffer = '';
  let waiting: { resolve: (text: string) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> } | null = null;
  let queue: Promise<unknown> = Promise.resolve();

  const fail = (error: Error): void => {
    if (waiting) {
      clearTimeout(waiting.timer);
      waiting.reject(error);
      waiting = null;
    }
  };

  const start = (): ChildProcessWithoutNullStreams => {
    if (helper && helper.exitCode === null) return helper;
    const encoded = Buffer.from(WINDOWS_HELPER, 'utf16le').toString('base64');
    const child = spawn('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded], {
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    buffer = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      buffer += chunk;
      const end = buffer.indexOf(END);
      if (end < 0 || !waiting) return;
      const answer = buffer.slice(0, end);
      buffer = buffer.slice(end + END.length).replace(/^\r?\n/, '');
      clearTimeout(waiting.timer);
      waiting.resolve(answer);
      waiting = null;
    });
    child.stderr.resume();
    child.on('error', (error) => fail(error));
    child.on('exit', () => {
      if (helper === child) helper = null;
      fail(new Error('PowerShell helper exited'));
    });
    helper = child;
    return child;
  };

  const ask = (request: string): Promise<string> => {
    const next = queue.then(() => new Promise<string>((resolve, reject) => {
      const child = start();
      const timer = setTimeout(() => {
        fail(new Error('PowerShell helper timed out'));
        child.kill();
      }, 15_000);
      waiting = { resolve, reject, timer };
      child.stdin.write(`${request}\n`);
    }));
    queue = next.catch(() => undefined);
    return next;
  };

  return {
    list: async () => parseWindowsList(await ask('list')),
    commands: async (pids) => {
      const commands = new Map<number, string>();
      for (const part of chunks(pids, 100)) {
        for (const [pid, command] of parseWindowsCommands(await ask(`commands ${part.join(',')}`))) commands.set(pid, command);
      }
      return commands;
    },
    ports: async (pids) => {
      const wanted = new Set(pids);
      const all = parseNetstatListen(await run('netstat', ['-ano']));
      return new Map([...all].filter(([pid]) => wanted.has(pid)));
    },
    memoryUsed: async () => freeMemoryFallback(),
    close: () => {
      fail(new Error('closed'));
      helper?.kill();
      helper = null;
    },
  };
};

export const createProcessSource = (): ProcessSource => {
  if (process.platform === 'win32') return windowsSource();
  if (process.platform === 'linux') return linuxSource();
  return psSource();
};
