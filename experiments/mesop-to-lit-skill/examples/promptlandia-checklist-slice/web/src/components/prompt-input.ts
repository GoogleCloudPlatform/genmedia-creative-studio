// prompt-input: the SHARED input promoted from the 4x copy-pasted
// gemini_prompt_input (DRY gate, component-decision-framework §4). Faithful port
// of Mesop's me.native_textarea -> a native <textarea> with native two-way
// binding, which DELETES the on_blur + prompt_textarea_key++ remount hack
// (target-architecture §5). Clear/send are icon buttons.
//
// Kept MWC-free so it is unit-testable under happy-dom; md-icon glyphs are styled
// by the global Material Symbols font and registered by the app entry.

import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('prompt-input')
export class PromptInput extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
    .wrap {
      display: flex;
      gap: 8px;
      border-radius: 16px;
      padding: 8px;
      background: var(--md-sys-color-surface-container-lowest, #fff);
      border: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
    }
    textarea {
      flex-grow: 1;
      border: none;
      outline: none;
      resize: vertical;
      min-height: 140px;
      padding: 12px;
      background: transparent;
      color: var(--md-sys-color-on-surface, #191c20);
      font: inherit;
    }
    .actions {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    button {
      border: none;
      background: transparent;
      cursor: pointer;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      color: var(--md-sys-color-primary, #415f91);
    }
    button:disabled {
      opacity: 0.4;
      cursor: default;
    }
    button:hover:not(:disabled) {
      background: var(--md-sys-color-surface-container-high, #e8eaef);
    }
  `;

  @property({ type: String }) value = '';
  @property({ type: String }) placeholder = 'Enter prompt to evaluate...';
  @property({ type: Boolean }) disabled = false;

  private onInput(e: Event) {
    this.value = (e.target as HTMLTextAreaElement).value;
    this.dispatchEvent(
      new CustomEvent('value-changed', {
        detail: { value: this.value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onSend() {
    if (this.disabled) return;
    this.dispatchEvent(
      new CustomEvent('send', {
        detail: { value: this.value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onClear() {
    this.value = '';
    this.dispatchEvent(
      new CustomEvent('clear', { bubbles: true, composed: true }),
    );
    this.dispatchEvent(
      new CustomEvent('value-changed', {
        detail: { value: '' },
        bubbles: true,
        composed: true,
      }),
    );
  }

  render() {
    return html`
      <div class="wrap">
        <textarea
          .value=${this.value}
          placeholder=${this.placeholder}
          ?disabled=${this.disabled}
          @input=${this.onInput}
        ></textarea>
        <div class="actions">
          <button
            aria-label="clear"
            ?disabled=${this.disabled}
            @click=${this.onClear}
          >
            <md-icon>clear</md-icon>
          </button>
          <button
            aria-label="send"
            ?disabled=${this.disabled}
            @click=${this.onSend}
          >
            <md-icon>send</md-icon>
          </button>
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'prompt-input': PromptInput;
  }
}
