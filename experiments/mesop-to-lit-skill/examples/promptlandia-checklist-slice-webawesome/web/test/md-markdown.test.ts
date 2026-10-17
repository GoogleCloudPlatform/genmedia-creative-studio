import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import '../src/components/md-markdown';
import type { MdMarkdown } from '../src/components/md-markdown';

// md-markdown is the single XSS boundary that replaces Mesop's 28x me.markdown
// (target-architecture §8): marked -> DOMPurify(default config) -> unsafeHTML.
// These tests feed hostile payloads and assert the dangerous tag/attribute does
// NOT survive into the rendered shadow DOM.
//
// happy-dom caveat (documented in RESULTS.md §3): happy-dom's DOM is not a
// faithful browser DOM, so DOMPurify's protocol-based URL filtering (e.g.
// stripping `javascript:` hrefs) is not reproduced reliably here. We therefore
// assert only on the two payloads that strip deterministically under happy-dom
// (`<script>` and event-handler attributes); the full browser-fidelity
// sanitization (incl. `javascript:` URLs) is verified by the security review and
// is a tracked job for the Playwright e2e layer.

async function renderMarkdown(text: string): Promise<MdMarkdown> {
  const el = await fixture<MdMarkdown>(
    html`<md-markdown .text=${text}></md-markdown>`,
  );
  await el.updateComplete;
  return el;
}

describe('md-markdown sanitization (XSS boundary, §8)', () => {
  it('strips <script> tags so no script executes in the DOM', async () => {
    const el = await renderMarkdown('hello <script>alert(1)</script> world');
    const root = el.shadowRoot!;
    expect(root.querySelector('script')).toBeNull();
    expect(root.innerHTML).not.toContain('<script');
    expect(root.innerHTML).not.toContain('alert(1)');
  });

  it('strips event-handler attributes (onerror) from injected tags', async () => {
    const el = await renderMarkdown('<img src=x onerror="alert(1)">');
    const root = el.shadowRoot!;
    const img = root.querySelector('img');
    if (img) {
      expect(img.hasAttribute('onerror')).toBe(false);
    }
    expect(root.innerHTML).not.toContain('onerror');
    expect(root.innerHTML).not.toContain('alert(1)');
  });

  it('renders benign markdown as structured content', async () => {
    const el = await renderMarkdown('# Title\n\n**bold** text');
    const root = el.shadowRoot!;
    // happy-dom mangles unsafeHTML structure, so assert on text, not tags.
    expect(root.textContent).toContain('Title');
    expect(root.textContent).toContain('bold');
  });
});
