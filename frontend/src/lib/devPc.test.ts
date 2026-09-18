import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  decodeIpv4Hex,
  isDevelopmentPcPublicIp,
  localMainScreenUrl,
  resolveShowDevMainButton,
} from './devPc';

describe('development PC gate', () => {
  it('decodes the allowlisted public IPv4', () => {
    assert.equal(decodeIpv4Hex('d2dc4ba5'), '210.220.75.165');
    assert.equal(isDevelopmentPcPublicIp('210.220.75.165'), true);
    assert.equal(isDevelopmentPcPublicIp('::ffff:210.220.75.165'), true);
    assert.equal(isDevelopmentPcPublicIp('1.2.3.4'), false);
  });

  it('shows the main-screen button on loopback or a remembered development PC', () => {
    assert.equal(resolveShowDevMainButton({ hostname: '127.0.0.1' }), true);
    assert.equal(resolveShowDevMainButton({ hostname: 'sonic-stream-teal.vercel.app' }), false);
    assert.equal(
      resolveShowDevMainButton({ hostname: 'sonic-stream-teal.vercel.app', search: '?devpc=1' }),
      true,
    );
    assert.equal(
      resolveShowDevMainButton({ hostname: 'sonic-stream-teal.vercel.app', stored: '1' }),
      true,
    );
    assert.equal(
      resolveShowDevMainButton({
        hostname: 'sonic-stream-teal.vercel.app',
        search: '?devpc=0',
        stored: '1',
      }),
      false,
    );
  });

  it('opens the local program from a public host and stays on-origin on loopback', () => {
    assert.equal(
      localMainScreenUrl('https://sonic-stream-teal.vercel.app', 'sonic-stream-teal.vercel.app'),
      'http://127.0.0.1:3000/',
    );
    assert.equal(localMainScreenUrl('http://127.0.0.1:3000', '127.0.0.1'), 'http://127.0.0.1:3000/');
  });
});
