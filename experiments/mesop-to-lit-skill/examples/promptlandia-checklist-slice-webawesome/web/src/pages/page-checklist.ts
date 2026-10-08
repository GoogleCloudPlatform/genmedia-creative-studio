// page-checklist: the pilot slice page (P1.6). Wires prompt-input ->
// await client.checklist() -> loading flag -> checklist-results. The Mesop
// generator-yield-for-spinner becomes async + a `loading` reactive flag
// (target-architecture §5/§6). Errors render from the uniform §3.5 envelope.

import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { client, ApiClientError } from '../api/client';
import type { ChecklistResponse } from '../api/types';
import '../components/app-header';
import '../components/prompt-input';
import '../components/checklist-results';

@customElement('page-checklist')
export class PageChecklist extends LitElement {
  static styles = css`
    :host {
      display: block;
      padding: 24px;
    }
    .intro {
      margin: 0 0 16px 0;
      color: var(--md-sys-color-on-background, #191c20);
    }
    .spacer {
      height: 16px;
    }
    .loading {
      display: grid;
      justify-items: center;
      gap: 8px;
      padding: 24px;
    }
    .error {
      color: var(--md-sys-color-error, #ba1a1a);
      font-weight: 700;
      padding: 12px 0;
    }
    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid var(--md-sys-color-outline-variant, #c4c6d0);
      border-top-color: var(--md-sys-color-primary, #415f91);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
  `;

  @state() private prompt = '';
  @state() private loading = false;
  @state() private result: ChecklistResponse | null = null;
  @state() private error: string | null = null;

  private onValueChanged(e: CustomEvent<{ value: string }>) {
    this.prompt = e.detail.value;
  }

  private onClear() {
    this.prompt = '';
    this.result = null;
    this.error = null;
  }

  private async onSend() {
    if (!this.prompt.trim() || this.loading) return;
    this.loading = true;
    this.error = null;
    this.result = null;
    try {
      this.result = await client.checklist(this.prompt);
    } catch (e) {
      this.error =
        e instanceof ApiClientError
          ? `${e.code}: ${e.message}`
          : 'Unexpected error';
    } finally {
      this.loading = false;
    }
  }

  render() {
    return html`
      <app-header heading="Prompt Health Checklist" icon="fact_check"></app-header>
      <p class="intro">
        Receive a quick checkup of your prompt using the prompt health checklist
      </p>
      <prompt-input
        .value=${this.prompt}
        ?disabled=${this.loading}
        @value-changed=${this.onValueChanged}
        @clear=${this.onClear}
        @send=${this.onSend}
      ></prompt-input>
      <div class="spacer"></div>
      ${this.loading
        ? html`
            <div class="loading">
              <div class="spinner"></div>
              <span>Linting prompt...</span>
            </div>
          `
        : nothing}
      ${this.error ? html`<div class="error">${this.error}</div>` : nothing}
      ${!this.loading && this.result
        ? html`<checklist-results .data=${this.result}></checklist-results>`
        : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'page-checklist': PageChecklist;
  }
}
