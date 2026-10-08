// page-stub: placeholder for the fan-out routes (settings/generate/trimmer/
// improver/video-checklist/playground) that are out of the mandatory pilot
// slice. They reuse this scaffold/router/theme when implemented (Phases 2-6).

import { LitElement, html, css } from 'lit';
import { customElement } from 'lit/decorators.js';
import '../components/app-header';

@customElement('page-stub')
export class PageStub extends LitElement {
  static styles = css`
    :host {
      display: block;
      padding: 24px;
      color: var(--md-sys-color-on-background, #191c20);
    }
  `;

  render() {
    return html`
      <app-header heading="Coming soon" icon="construction"></app-header>
      <p>
        This page is part of the conversion fan-out (Phases 2-6) and is not in the
        mandatory pilot slice. The checklist slice proves the scaffold it will reuse.
      </p>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'page-stub': PageStub;
  }
}
