/**
 * Copyright 2026 Google LLC
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

import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'

import './components/concept-sidebar'
import './components/variation-tile'
import './components/niqe-modal'

@customElement('variations-app')
export class VariationsApp extends LitElement {
  @state() private status: string = 'idle'
  @state() private jobId: string | null = null
  @state() private variations: any[] = []
  @state() private error: string | null = null
  @state() private showNiqeModal: boolean = false
  @state() private selectedNiqeVariation: any = null

  private get apiBase() {
    if (window.location.hostname === 'localhost' && window.location.port !== '8000') {
      return 'http://localhost:8000'
    }
    return ''
  }

  static styles = css`
    :host {
      display: grid;
      grid-template-columns: 380px 1fr;
      height: 100vh;
      overflow: hidden;
    }

    main {
      padding: 3rem;
      overflow-y: auto;
      background-color: #0a0a0a;
      display: flex;
      flex-direction: column;
      gap: 2rem;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      grid-auto-rows: 1fr;
      gap: 2rem;
    }

    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    h1 {
      font-family: 'Manrope', sans-serif;
      font-weight: 800;
      font-size: 1.8rem;
      margin: 0;
      color: #fff;
    }

    .status-tag {
      font-size: 0.8rem;
      font-weight: 600;
      color: #4285F4;
      background: rgba(66, 133, 244, 0.1);
      padding: 4px 12px;
      border-radius: 20px;
    }

    .niqe-info-btn {
      background: #161616;
      border: 1px solid #333;
      color: #aaa;
      font-family: 'Inter', sans-serif;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 999px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      transition: all 0.15s;
    }

    .niqe-info-btn:hover {
      border-color: #4285F4;
      color: #fff;
      background: rgba(66, 133, 244, 0.1);
    }
  `

  async handleGenerate(e: CustomEvent) {
    const { prompt, count, aspectRatio, model, image } = e.detail
    this.status = 'initializing'
    this.error = null
    this.variations = Array.from({ length: count }, (_, i) => ({ id: i, status: 'generating', prompt: 'Preparing...' }))
    
    const formData = new FormData()
    formData.append('prompt', prompt)
    formData.append('count', count.toString())
    formData.append('aspect_ratio', aspectRatio)
    if (model) formData.append('model', model)
    if (image) formData.append('image', image)

    try {
      const resp = await fetch(`${this.apiBase}/variations`, {
        method: 'POST',
        body: formData
      })
      const data = await resp.json()
      this.jobId = data.job_id
      this.poll()
    } catch (err: any) {
      this.error = err.message
      this.status = 'failed'
    }
  }

  async poll() {
    if (!this.jobId) return
    const check = async () => {
      try {
        const resp = await fetch(`${this.apiBase}/jobs/${this.jobId}`)
        const data = await resp.json()
        this.status = data.status
        
        if (data.results?.variations) {
          // Merge results
          this.variations = data.results.variations
        }

        if (data.status === 'completed' || data.status === 'failed') {
          if (data.status === 'failed') this.error = data.error
          return
        }
        
        setTimeout(check, 3000)
      } catch (err: any) {
        this.error = err.message
        this.status = 'failed'
      }
    }
    check()
  }

  private openNiqeModal(variation: any = null) {
    this.selectedNiqeVariation = variation
    this.showNiqeModal = true
  }

  render() {
    return html`
      <concept-sidebar @generate=${this.handleGenerate}></concept-sidebar>
      
      <main @open-niqe=${(e: CustomEvent) => this.openNiqeModal(e.detail)}>
        <div class="header">
          <h1>Variations Canvas</h1>
          <div class="header-actions">
            ${this.status !== 'idle' ? html`<div class="status-tag">${this.status}</div>` : ''}
            <button class="niqe-info-btn" @click=${() => this.openNiqeModal(null)}>
              <span style="color: #4285F4;">ⓘ</span> What is NIQE?
            </button>
          </div>
        </div>

        ${this.error ? html`<div style="color: #ea4335; background: rgba(234, 67, 53, 0.1); padding: 1rem; border-radius: 8px;">${this.error}</div>` : ''}

        <div class="grid">
          ${this.variations.map(v => html`
            <variation-tile .data=${v} .apiBase=${this.apiBase}></variation-tile>
          `)}
          ${this.variations.length === 0 ? html`
            <div style="grid-column: 1/-1; text-align: center; color: #444; padding-top: 10vh;">
              <div style="font-size: 3rem; margin-bottom: 1rem;">✨</div>
              <div style="font-family: Manrope; font-weight: 600;">Define a concept to start generating variations</div>
            </div>
          ` : ''}
        </div>
      </main>

      <niqe-modal
        .open=${this.showNiqeModal}
        .variation=${this.selectedNiqeVariation}
        @close=${() => { this.showNiqeModal = false; this.selectedNiqeVariation = null; }}
      ></niqe-modal>
    `
  }
}
