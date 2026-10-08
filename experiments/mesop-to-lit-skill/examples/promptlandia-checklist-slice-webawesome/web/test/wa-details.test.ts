import 'element-internals-polyfill';
import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import '@awesome.me/webawesome/dist/components/details/details.js';
import type WaDetails from '@awesome.me/webawesome/dist/components/details/details.js';

async function mount(open = false): Promise<WaDetails> {
  const el = await fixture<WaDetails>(
    html`<wa-details summary="Category Details" ?open=${open}>
      <p>details body</p>
    </wa-details>`,
  );
  await el.updateComplete;
  return el;
}

describe('wa-details (stock Web Awesome accordion replacement)', () => {
  it('renders summary and slotted content', async () => {
    const el = await mount();
    expect(el.summary).toBe('Category Details');
    expect(el.textContent).toContain('details body');
  });

  it('is closed by default', async () => {
    const el = await mount();
    expect(el.open).toBe(false);
  });

  it('reflects open state when set', async () => {
    const el = await mount(true);
    expect(el.open).toBe(true);
  });
});
