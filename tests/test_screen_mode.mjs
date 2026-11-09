import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';

const source = stripTypeScriptTypes(
  readFileSync(new URL('../src/screen-mode.ts', import.meta.url), 'utf8').replace('export {};', ''),
);

function screen(time, { storage = new Map(), dialog = false, storageDenied = false } = {}) {
  let now = new Date(time).getTime();
  let black = false;
  let exits = 0;
  let tick;
  let ready;
  const listeners = {};
  const listen = (type, handler) => { (listeners[type] ??= []).push(handler); };
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [now])); }
  }
  const context = {
    exports: {}, Date: Clock,
    sessionStorage: {
      getItem(key) { if (storageDenied) throw Error('Denied'); return storage.get(key) ?? null; },
      setItem(key, value) { if (storageDenied) throw Error('Denied'); storage.set(key, value); },
      removeItem(key) { if (storageDenied) throw Error('Denied'); storage.delete(key); },
    },
    document: {
      documentElement: { classList: { toggle(name, value) { assert.equal(name, 'night-black'); black = value; } } },
      querySelector: () => dialog ? {} : null,
      addEventListener: listen,
    },
    window: { addEventListener: listen, close: () => { exits++; } },
    setTimeout: callback => { ready = callback; },
    setInterval: callback => { tick = callback; },
  };
  vm.runInNewContext(source, context);
  return {
    get black() { return black; }, get exits() { return exits; },
    ready: () => ready(),
    at(time) { now = new Date(time).getTime(); tick(); },
    event(type, properties = {}) {
      let consumed = false;
      const event = {
        code: 'Space', repeat: false, ...properties,
        preventDefault() { consumed = true; }, stopImmediatePropagation() {},
      };
      for (const handler of listeners[type] ?? []) handler(event);
      return consumed;
    },
  };
}

test('18:10 enters black and 06:00 restores the clock across midnight', () => {
  const page = screen('2026-10-01T18:09:59');
  assert.equal(page.black, false);
  page.at('2026-10-01T18:10:00');
  assert.equal(page.black, true);
  page.at('2026-10-02T00:00:00');
  assert.equal(page.black, true);
  page.at('2026-10-02T05:59:59');
  assert.equal(page.black, true);
  page.at('2026-10-02T06:00:00');
  assert.equal(page.black, false);
});

test('first press only wakes; held key and key release cannot exit; second press exits', () => {
  const page = screen('2026-10-01T22:00:00');
  page.ready();
  assert.equal(page.event('keydown'), true);
  assert.equal(page.black, false);
  assert.equal(page.exits, 0);
  assert.equal(page.event('keydown', { repeat: true }), true);
  assert.equal(page.exits, 0);
  assert.equal(page.event('keyup'), true);
  page.event('keydown');
  assert.equal(page.exits, 1);
});

test('wake works immediately after launch but daytime retains startup grace', () => {
  const night = screen('2026-10-01T18:10:00');
  night.event('keydown');
  assert.equal(night.black, false);
  assert.equal(night.exits, 0);
  const day = screen('2026-10-01T09:00:00');
  day.event('keydown');
  assert.equal(day.exits, 0);
  day.ready();
  day.event('keydown');
  assert.equal(day.exits, 1);
});

test('night override survives midnight and frontend reload but resets next evening', () => {
  const storage = new Map();
  const page = screen('2026-10-01T22:00:00', { storage });
  page.event('keydown');
  page.at('2026-10-02T02:00:00');
  assert.equal(page.black, false);
  const reloaded = screen('2026-10-02T02:00:00', { storage });
  assert.equal(reloaded.black, false);
  reloaded.at('2026-10-02T06:00:00');
  assert.equal(storage.size, 0);
  reloaded.at('2026-10-02T18:10:00');
  assert.equal(reloaded.black, true);
  assert.equal(screen('2026-10-01T22:00:00').black, true);
});

test('first Escape wakes an open dialog without closing it; next key passes through', () => {
  const page = screen('2026-10-01T22:00:00', { dialog: true });
  page.ready();
  assert.equal(page.event('keydown', { code: 'Escape' }), true);
  assert.equal(page.black, false);
  page.event('keyup', { code: 'Escape' });
  assert.equal(page.event('keydown', { code: 'Escape' }), false);
  assert.equal(page.exits, 0);
});

test('wake override also works when browser storage is unavailable', () => {
  const page = screen('2026-10-01T22:00:00', { storageDenied: true });
  page.event('keydown');
  page.at('2026-10-02T05:59:59');
  assert.equal(page.black, false);
  page.at('2026-10-02T18:10:00');
  assert.equal(page.black, true);
});

test('month rollover and missed timer ticks still use the correct night', () => {
  const page = screen('2026-12-31T23:00:00');
  page.event('keydown');
  page.at('2027-01-01T05:59:59');
  assert.equal(page.black, false);
  page.at('2027-01-01T18:10:00');
  assert.equal(page.black, true);
});
