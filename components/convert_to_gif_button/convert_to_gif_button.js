/**
 * Copyright 2025 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { LitElement, html, css } from 'https://cdn.jsdelivr.net/npm/lit/+esm';
import 'https://cdn.jsdelivr.net/npm/@material/mwc-button/+esm';

class ConvertToGifButton extends LitElement {
  static get properties() {
    return {
      url: { type: String },
      converting: { type: Boolean, state: true },
      converted: { type: Boolean, state: true },
      error: { type: String, state: true },
    };
  }

  constructor() {
    super();
    this.url = '';
    this.converting = false;
    this.converted = false;
    this.error = '';
  }

  static styles = css`
    .error-message {
        color: var(--mat-sys-color-error, #B00020);
        font-size: 12px;
        margin-top: 4px;
    }
  `;

  async _handleConvert() {
    if (!this.url || !this.url.startsWith('gs://')) {
      this.error = 'Error: Invalid GCS URI provided.';
      return;
    }
    this.converting = true;
    this.error = null;
    let gifUrl = null;

    try {
      const covertResponse = await fetch(`/api/convert_to_gif?gcs_uri=${encodeURIComponent(this.url)}`);

      if (!covertResponse.ok || covertResponse.error)
        throw new Error(covertResponse.error || `API error! status: ${covertResponse.status}`);
      
      const convertData = await covertResponse.json();
      gifUrl = convertData.url;

      if (!gifUrl) {
        throw new Error('Failed to convert video to GIF.');
      }

      this.converted = true;

      console.log('Conversion successful. GIF URL:', gifUrl);
    } catch (e) {
      console.error('Conversion failed:', e);
      this.converted = false;
      this.error = e.message || `Converstion failed.`;
    } finally {
      this.dispatchEvent(new CustomEvent('conversion-complete', { bubbles: true, composed: true, detail: { error: this.error, url: gifUrl } }));
      this.converting = false;
    }
  }

  render() {
    let label, disabled;

    if (this.converted) {
      label = 'converted'
      disabled = true;
    }
    else if (this.converting){
      label = 'converting...';
      disabled = true;
    }
    else {
      label = 'convert to gif';
      disabled = false
    }

    const iconSvg = this.converting
      ? html`<svg slot="icon" xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M12 6v3l4-4-4-4v3c-4.42 0-8 3.58-8 8 0 1.57.46 3.03 1.24 4.26L6.7 14.8c-.45-.83-.7-1.79-.7-2.8 0-3.31 2.69-6 6-6zm6.76 1.74L17.3 9.2c.44.84.7 1.79.7 2.8 0 3.31-2.69 6-6 6v-3l-4 4 4 4v-3c4.42 0 8-3.58 8-8 0-1.57-.46-3.03-1.24-4.26z"/></svg>`
      : html`<svg slot="icon" xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 0 24 24" width="18px" fill="currentColor"><path d="M0 0h24v24H0V0z" fill="none"/><path d="M19,3H5C3.9,3,3,3.9,3,5v14c0,1.1,0.9,2,2,2h14c1.1,0,2-0.9,2-2V5C21,3.9,20.1,3,19,3z M9.5,13v-1h1v1c0,0.55-0.45,1-1,1h-1 c-0.55,0-1-0.45-1-1v-2c0-0.55,0.45-1,1-1h1c0.55,0,1,0.45,1,1h-2v2H9.5z M12.5,14h-1v-4h1V14z M16.5,11h-2v0.5H16v1h-1.5V14h-1v-4 h3V11z"/></svg>`;

    return html`
      <mwc-button
        outlined
        @click="${this._handleConvert}"
        ?disabled="${disabled}">
        ${iconSvg}
        <span>${label}</span>
      </mwc-button>
      ${this.error ? html`<p class="error-message">${this.error}</p>` : ''}
    `;
  }
}

customElements.define('convert-to-gif-button', ConvertToGifButton);