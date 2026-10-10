// app-sidenav: CUSTOM collapsible navigation (component-decision-framework #10).
// md-navigation-drawer is LABS-only in a maintenance-mode lib (rejected §0), so
// we build the nav from a plain native <ul>/<a> list (styled here) plus the
// STABLE md-icon-button + md-icon glyphs, under a custom wrapper that owns the
// mini<->expanded collapse state + the theme toggle. (md-list wrapping a <ul> is
// redundant nested-list semantics, so it is not used.)
// Index-keyed Mesop nav -> a declarative route table.

import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { NAV_ITEMS } from '../router';
import { resolveMode, toggleTheme, type ThemeMode } from '../theme';

@customElement('app-sidenav')
export class AppSidenav extends LitElement {
  static styles = css`
    :host {
      display: block;
      height: 100%;
    }
    nav {
      display: flex;
      flex-direction: column;
      height: 100%;
      background: var(--md-sys-color-surface-container, #eef0f5);
      border-right: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
      width: 240px;
      transition: width 0.2s ease;
      box-sizing: border-box;
    }
    :host([collapsed]) nav {
      width: 72px;
    }
    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px;
    }
    .brand {
      font-weight: 700;
      padding-left: 8px;
      white-space: nowrap;
    }
    :host([collapsed]) .brand {
      display: none;
    }
    ul {
      list-style: none;
      margin: 0;
      padding: 0;
      flex-grow: 1;
    }
    a {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 12px 20px;
      color: var(--md-sys-color-on-surface, #191c20);
      text-decoration: none;
      white-space: nowrap;
    }
    a:hover {
      background: var(--md-sys-color-surface-container-high, #e8eaef);
    }
    a.active {
      background: var(--md-sys-color-primary, #415f91);
      color: var(--md-sys-color-on-primary, #fff);
    }
    :host([collapsed]) a .label {
      display: none;
    }
    .bottom {
      padding: 8px;
      border-top: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
    }
    .collapse-btn {
      background: transparent;
      border: none;
      cursor: pointer;
      padding: 8px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: inherit;
    }
    .collapse-btn:hover {
      background: var(--md-sys-color-surface-container-high, #e8eaef);
    }
  `;

  @property({ type: Boolean, reflect: true }) collapsed = false;
  @property({ type: String }) activePath = '/checklist';
  @state() private mode: ThemeMode = resolveMode();

  private onToggleCollapse() {
    this.collapsed = !this.collapsed;
  }

  private onToggleTheme() {
    this.mode = toggleTheme();
  }

  render() {
    return html`
      <nav>
        <div class="top">
          <span class="brand brand-gradient">Promptlandia</span>
          <button
            class="collapse-btn"
            aria-label="toggle navigation"
            @click=${this.onToggleCollapse}
          >
            <span class="material-symbols-outlined">${this.collapsed ? 'menu' : 'menu_open'}</span>
          </button>
        </div>
        <ul>
          ${NAV_ITEMS.map(
            (item) => html`
              <li>
                <a
                  href=${item.path}
                  class=${this.activePath === item.path ? 'active' : ''}
                  title=${item.label}
                >
                  <span class="material-symbols-outlined">${item.icon}</span>
                  <span class="label">${item.label}</span>
                </a>
              </li>
            `,
          )}
        </ul>
        <div class="bottom">
          <button
            class="collapse-btn"
            aria-label="toggle theme"
            @click=${this.onToggleTheme}
          >
            <span class="material-symbols-outlined">${this.mode === 'dark' ? 'light_mode' : 'dark_mode'}</span>
          </button>
        </div>
      </nav>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-sidenav': AppSidenav;
  }
}
