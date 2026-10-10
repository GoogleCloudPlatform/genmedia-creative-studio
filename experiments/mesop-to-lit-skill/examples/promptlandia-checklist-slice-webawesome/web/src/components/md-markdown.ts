// md-markdown: render markdown -> sanitized HTML (target-architecture §4.3).
// marked does the parsing; DOMPurify is the mandatory sanitization step (we
// control rendering, so Trusted Types is not required -- §8). Replaces Mesop's
// 28x me.markdown.

import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

@customElement('md-markdown')
export class MdMarkdown extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
    .md :first-child {
      margin-top: 0;
    }
    .md :last-child {
      margin-bottom: 0;
    }
    .md code {
      background: var(--md-sys-color-surface-container-high, #eee);
      border-radius: 4px;
      padding: 0 4px;
    }
    .md pre {
      overflow-x: auto;
    }
  `;

  @property({ type: String }) text = '';

  private render_html(): string {
    const raw = marked.parse(this.text ?? '', { async: false }) as string;
    return DOMPurify.sanitize(raw);
  }

  render() {
    return html`<div class="md">${unsafeHTML(this.render_html())}</div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'md-markdown': MdMarkdown;
  }
}
