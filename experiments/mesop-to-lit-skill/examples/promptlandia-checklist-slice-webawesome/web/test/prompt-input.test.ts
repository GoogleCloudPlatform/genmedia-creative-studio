import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import '../src/components/prompt-input';
import type { PromptInput } from '../src/components/prompt-input';

async function mount(): Promise<PromptInput> {
  const el = await fixture<PromptInput>(
    html`<prompt-input></prompt-input>`,
  );
  await el.updateComplete;
  return el;
}

function button(el: PromptInput, label: string): HTMLButtonElement {
  return el.shadowRoot!.querySelector(
    `button[aria-label="${label}"]`,
  ) as HTMLButtonElement;
}

describe('prompt-input', () => {
  it('shows the Mesop placeholder', async () => {
    const el = await mount();
    const ta = el.shadowRoot!.querySelector('textarea')!;
    expect(ta.placeholder).toBe('Enter prompt to evaluate...');
  });

  it('emits value-changed on input (native two-way binding)', async () => {
    const el = await mount();
    const ta = el.shadowRoot!.querySelector('textarea')!;
    let got = '';
    el.addEventListener('value-changed', (e) => {
      got = (e as CustomEvent).detail.value;
    });
    ta.value = 'hello prompt';
    ta.dispatchEvent(new Event('input'));
    expect(got).toBe('hello prompt');
    expect(el.value).toBe('hello prompt');
  });

  it('emits send with the current value', async () => {
    const el = await mount();
    el.value = 'evaluate me';
    await el.updateComplete;
    let sent: string | null = null;
    el.addEventListener('send', (e) => {
      sent = (e as CustomEvent).detail.value;
    });
    button(el, 'send').click();
    expect(sent).toBe('evaluate me');
  });

  it('clears the value and emits clear', async () => {
    const el = await mount();
    el.value = 'something';
    await el.updateComplete;
    let cleared = false;
    el.addEventListener('clear', () => {
      cleared = true;
    });
    button(el, 'clear').click();
    expect(cleared).toBe(true);
    expect(el.value).toBe('');
  });

  it('does not emit send when disabled', async () => {
    const el = await mount();
    el.value = 'x';
    el.disabled = true;
    await el.updateComplete;
    let sent = false;
    el.addEventListener('send', () => {
      sent = true;
    });
    button(el, 'send').click();
    expect(sent).toBe(false);
  });
});
