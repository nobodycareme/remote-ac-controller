// Regression test for the WEB_REAL_IR_ENABLED boolean-parsing bug.
// z.coerce.boolean() silently turned the STRING "false" into `true` (Boolean("false")
// is truthy), which kept the real-IR kill switch ON even when an operator set it to
// "false". The schema now parses the raw string explicitly. These tests prove the
// kill switch is genuinely OFF for any non-"true" value.
import { describe, it, expect, vi, afterEach } from 'vitest';

async function configWith(envValue: string | undefined) {
  if (envValue === undefined) delete (process.env as any).WEB_REAL_IR_ENABLED;
  else process.env.WEB_REAL_IR_ENABLED = envValue;
  vi.resetModules();
  return (await import('../src/config')).config;
}

describe('WEB_REAL_IR_ENABLED strict boolean parsing', () => {
  it('env "false" MUST parse to false (the original bug)', async () => {
    const cfg = await configWith('false');
    expect(cfg.WEB_REAL_IR_ENABLED).toBe(false);
  });

  it('env "true" parses to true', async () => {
    const cfg = await configWith('true');
    expect(cfg.WEB_REAL_IR_ENABLED).toBe(true);
  });

  it('env "1" parses to true; "0"/"off"/""/"FALSE" parse to false', async () => {
    expect((await configWith('1')).WEB_REAL_IR_ENABLED).toBe(true);
    for (const v of ['0', 'off', '', 'FALSE', 'no']) {
      expect((await configWith(v)).WEB_REAL_IR_ENABLED).toBe(false);
    }
  });

  it('unset env defaults to false', async () => {
    const cfg = await configWith(undefined);
    expect(cfg.WEB_REAL_IR_ENABLED).toBe(false);
  });

  afterEach(() => {
    delete (process.env as any).WEB_REAL_IR_ENABLED;
    vi.resetModules();
  });
});
