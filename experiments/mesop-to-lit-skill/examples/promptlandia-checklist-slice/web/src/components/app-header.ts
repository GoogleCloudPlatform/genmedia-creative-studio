// app-header: title + leading icon (component-decision-framework #12). Thin
// shared element; one instance per page.

import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('app-header')
export class AppHeader extends LitElement {
  static styles = css`
    :host {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 8px;
    }
    .title {
      font-size: 24px;
      font-weight: 500;
      color: var(--md-sys-color-on-background, #191c20);
    }
    md-icon {
      color: var(--md-sys-color-primary, #415f91);
    }
  `;

  @property({ type: String }) heading = '';
  @property({ type: String }) icon = '';

  render() {
    return html`
      ${this.icon ? html`<md-icon>${this.icon}</md-icon>` : ''}
      <span class="title">${this.heading}</span>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-header': AppHeader;
  }
}
