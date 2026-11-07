import { describe, expect, test } from 'bun:test';

import {
  parseCmdline,
  parseCpuTime,
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
} from './parse.ts';

describe('macOS', () => {
  test('cputime in every shape ps prints', () => {
    expect(parseCpuTime('0:01.25')).toBeCloseTo(1.25);
    expect(parseCpuTime('18:29.43')).toBeCloseTo(18 * 60 + 29.43);
    expect(parseCpuTime('1:02:03')).toBe(3723);
    expect(parseCpuTime('2-01:00:00')).toBe(2 * 86_400 + 3600);
    expect(parseCpuTime('x')).toBeNaN();
  });

  test('ps list keeps names with spaces', () => {
    const rows = parsePsList([
      '    1     0  18160  18:29.43 ??       /sbin/launchd',
      '41761 41745 556032   1:02.10 ??       /Applications/OpenDiscovery.app/Contents/Frameworks/OpenDiscovery Helper (Renderer).app/Contents/MacOS/OpenDiscovery Helper (Renderer)',
      '52000 41745  90000   0:03.00 ttys004  node',
      'garbage',
    ].join('\n'));
    expect(rows).toHaveLength(3);
    expect(rows[1]).toEqual({ pid: 41761, ppid: 41745, name: 'OpenDiscovery Helper (Renderer)', memory: 556032 * 1024, cpuSeconds: 62.1 });
    expect(rows[2]).toMatchObject({ pid: 52000, name: 'node', tty: 'ttys004' });
  });

  test('ps commands', () => {
    expect(parsePsCommands(' 12 node vite --port 5173\n13 \n')).toEqual(new Map([[12, 'node vite --port 5173'], [13, '']]));
  });

  test('vm_stat counts memory the way Activity Monitor does', () => {
    const stdout = [
      'Mach Virtual Memory Statistics: (page size of 16384 bytes)',
      'Pages free:                                    24210.',
      'Pages wired down:                             177163.',
      'Pages purgeable:                                2212.',
      'Anonymous pages:                              368257.',
      'Pages occupied by compressor:                 268831.',
    ].join('\n');
    expect(parseVmStatUsed(stdout)).toBe((368257 - 2212 + 177163 + 268831) * 16384);
    expect(parseVmStatUsed('nothing useful')).toBeNull();
  });

  test('lsof listeners per pid, IPv4 and IPv6, no duplicates', () => {
    const ports = parseLsofListen(['p100', 'f20', 'n*:5173', 'f21', 'n[::1]:5173', 'p200', 'f7', 'n127.0.0.1:3000'].join('\n'));
    expect(ports).toEqual(new Map([[100, [5173]], [200, [3000]]]));
  });
});

describe('Linux', () => {
  test('stat with spaces and parentheses in the name', () => {
    const withTty = parseLinuxStat(`77 (node) ${['S', '41', '77', '77', '34817', ...Array.from({ length: 17 }, () => '0')].join(' ')}`, 100, 4096);
    expect(withTty?.tty).toBe('34817');
    const fields = ['S', '41', '1', '1', '0', '-1', '0', '0', '0', '0', '0', '250', '50', '0', '0', '20', '0', '1', '0', '100', '1000', '300'];
    const row = parseLinuxStat(`4242 (my (odd) proc) ${fields.join(' ')}`, 100, 4096);
    expect(row).toEqual({ pid: 4242, ppid: 41, name: 'my (odd) proc', memory: 300 * 4096, cpuSeconds: 3 });
    expect(parseLinuxStat('nonsense', 100, 4096)).toBeNull();
  });

  test('cmdline', () => {
    expect(parseCmdline('node\0server.js\0--port\x003000\0')).toBe('node server.js --port 3000');
  });

  test('meminfo', () => {
    expect(parseMeminfoUsed('MemTotal:       16000000 kB\nMemFree: 1 kB\nMemAvailable:    6000000 kB\n')).toBe(10_000_000 * 1024);
    expect(parseMeminfoUsed('MemTotal: 1 kB')).toBeNull();
  });

  test('only listening sockets from /proc/net/tcp', () => {
    const table = [
      '  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode',
      '   0: 00000000:1435 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 55501 1 0000000000000000 100 0 0 10 0',
      '   1: 0100007F:0BB8 0100007F:A1B2 01 00000000:00000000 00:00000000 00000000  1000        0 55502 1 0000000000000000 20 4 30 10 -1',
    ].join('\n');
    expect(parseProcNetTcp(table)).toEqual(new Map([['55501', 5173]]));
    expect(socketInode('socket:[55501]')).toBe('55501');
    expect(socketInode('/dev/null')).toBeNull();
  });
});

describe('Windows', () => {
  test('netstat listeners by empty remote end, in any language', () => {
    const stdout = [
      'Active Connections',
      '',
      '  Proto  Local Address          Foreign Address        State           PID',
      '  TCP    0.0.0.0:5173           0.0.0.0:0              ABHÖREN         4100',
      '  TCP    127.0.0.1:52000        127.0.0.1:5173         HERGESTELLT     4200',
      '  TCP    [::]:3000              [::]:0                 LISTENING       4300',
      '  UDP    0.0.0.0:5353           *:*                                    4400',
    ].join('\r\n');
    expect(parseNetstatListen(stdout)).toEqual(new Map([[4100, [5173]], [4300, [3000]]]));
  });

  test('helper process list and command lines', () => {
    expect(parseWindowsList('4\t0\t1048576\t20000000\t\tSystem\r\n8120\t4\t2097152\t5000000\t1792070000000\tnode.exe\r\n')).toEqual([
      { pid: 4, ppid: 0, name: 'System', memory: 1048576, cpuSeconds: 2 },
      { pid: 8120, ppid: 4, name: 'node.exe', memory: 2097152, cpuSeconds: 0.5, startedAt: 1792070000000 },
    ]);
    expect(parseWindowsCommands('8120\t"C:\\node.exe" vite\r\n9\t\r\n')).toEqual(new Map([[8120, '"C:\\node.exe" vite'], [9, '']]));
  });
});
