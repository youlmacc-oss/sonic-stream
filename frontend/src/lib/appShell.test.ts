import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { getServerAppShell, getServerShowDevMainButton, isDevPcHost, resolveAppShell } from './appShell';

describe('app shell', () => {
  it('keeps a stable boot snapshot for the first server render', () => {
    assert.equal(getServerAppShell(), 'boot');
    assert.equal(getServerAppShell(), 'boot');
  });

  it('treats the public host and ?install=1 as the install shell', () => {
    assert.equal(resolveAppShell('sonic-stream-teal.vercel.app'), 'public');
    assert.equal(resolveAppShell('127.0.0.1', '?install=1'), 'public');
    assert.equal(resolveAppShell('localhost', '?install=1'), 'public');
  });

  it('shows the local program with ?devpc=1 on public hosts', () => {
    assert.equal(resolveAppShell('sonic-stream-teal.vercel.app', '?devpc=1'), 'local');
    assert.equal(resolveAppShell('sonic-stream-teal.vercel.app', '?devpc=1&other=test'), 'local');
    assert.equal(resolveAppShell('sonic-stream-teal.vercel.app', '?install=1&devpc=1'), 'public'); // install takes priority
  });

  it('keeps loopback hosts on the local program shell', () => {
    assert.equal(resolveAppShell('127.0.0.1'), 'local');
    assert.equal(resolveAppShell('localhost'), 'local');
    assert.equal(resolveAppShell('::1'), 'local');
    assert.equal(resolveAppShell('[::1]'), 'local');
  });

  it('treats only loopback as a development PC host name', () => {
    assert.equal(getServerShowDevMainButton(), false);
    assert.equal(isDevPcHost('127.0.0.1'), true);
    assert.equal(isDevPcHost('localhost'), true);
    assert.equal(isDevPcHost('::1'), true);
    assert.equal(isDevPcHost('sonic-stream-teal.vercel.app'), false);
  });
});
