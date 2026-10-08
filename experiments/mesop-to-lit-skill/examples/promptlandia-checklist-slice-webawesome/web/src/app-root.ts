// app-root: the app shell (component-decision-framework #11; Q3 compose). Lays
// out the custom sidenav + a <main> router outlet, owns the router, and keeps the
// active nav path in sync with navigation.

import { LitElement, html, css } from 'lit';
import { customElement, query, state } from 'lit/decorators.js';
import { initRouter } from './router';
import './components/app-sidenav';

@customElement('app-root')
export class AppRoot extends LitElement {
  static styles = css`
    :host {
      display: flex;
      height: 100vh;
      width: 100vw;
    }
    main {
      flex-grow: 1;
      overflow-y: auto;
      background: var(--md-sys-color-background, #fff);
    }
  `;

  @query('main') private outlet!: HTMLElement;
  @state() private activePath = window.location.pathname;

  firstUpdated() {
    initRouter(this.outlet);
    window.addEventListener('vaadin-router-location-changed', (e) => {
      const loc = (e as CustomEvent).detail?.location;
      if (loc?.pathname) this.activePath = loc.pathname;
    });
  }

  render() {
    return html`
      <app-sidenav .activePath=${this.activePath}></app-sidenav>
      <main></main>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-root': AppRoot;
  }
}
