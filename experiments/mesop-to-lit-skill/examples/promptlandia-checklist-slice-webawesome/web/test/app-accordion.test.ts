import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import '../src/components/app-accordion';
import type { AppAccordion } from '../src/components/app-accordion';

async function mount(open = false): Promise<AppAccordion> {
  const el = await fixture<AppAccordion>(
    html`<app-accordion heading="Details" ?open=${open}>
      <p>panel body</p>
    </app-accordion>`,
  );
  await el.updateComplete;
  return el;
}

describe('app-accordion', () => {
  it('renders heading and slotted content', async () => {
    const el = await mount();
    expect(el.shadowRoot!.querySelector('summary')!.textContent).toContain(
      'Details',
    );
    expect(el.querySelector('p')!.textContent).toBe('panel body');
  });

  it('is closed by default', async () => {
    const el = await mount();
    const details = el.shadowRoot!.querySelector('details')!;
    expect(details.open).toBe(false);
  });

  it('reflects the open property to the native details', async () => {
    const el = await mount(true);
    const details = el.shadowRoot!.querySelector('details')!;
    expect(details.open).toBe(true);
  });

  it('emits toggle with the new open state on native toggle', async () => {
    const el = await mount();
    const details = el.shadowRoot!.querySelector('details')!;
    let openState: boolean | null = null;
    el.addEventListener('toggle', (e) => {
      openState = (e as unknown as CustomEvent).detail.open;
    });
    details.open = true;
    details.dispatchEvent(new Event('toggle'));
    expect(openState).toBe(true);
    expect(el.open).toBe(true);
  });
});
