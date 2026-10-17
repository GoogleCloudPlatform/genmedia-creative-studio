// app-accordion: custom expansion panel over native <details>/<summary>
// (target-architecture §4.3; MWC has no accordion -> build custom, LIVE-confirmed
// absent). Native <details> gives a11y + open/close state for free; we style it
// with M3 tokens and emit a `toggle` event carrying the open state.

import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('app-accordion')
export class AppAccordion extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
    details {
      border: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
      border-radius: 12px;
      background: var(--md-sys-color-surface-container, #eef0f5);
      overflow: hidden;
    }
    summary {
      cursor: pointer;
      padding: 12px 16px;
      font-weight: 500;
      list-style: none;
      user-select: none;
      color: var(--md-sys-color-on-surface, #191c20);
    }
    summary::-webkit-details-marker {
      display: none;
    }
    summary::after {
      content: 'expand_more';
      font-family: 'Material Symbols Outlined';
      float: right;
      transition: transform 0.2s ease;
    }
    details[open] summary::after {
      transform: rotate(180deg);
    }
    .body {
      padding: 0 16px 16px 16px;
    }
  `;

  @property({ type: String }) heading = '';
  @property({ type: Boolean, reflect: true }) open = false;

  private onToggle(e: Event) {
    this.open = (e.target as HTMLDetailsElement).open;
    this.dispatchEvent(
      new CustomEvent('toggle', {
        detail: { open: this.open },
        bubbles: true,
        composed: true,
      }),
    );
  }

  render() {
    return html`
      <details ?open=${this.open} @toggle=${this.onToggle}>
        <summary>${this.heading}</summary>
        <div class="body"><slot></slot></div>
      </details>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-accordion': AppAccordion;
  }
}
