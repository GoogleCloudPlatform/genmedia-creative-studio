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
import { customElement, property } from 'lit/decorators.js'

@customElement('niqe-modal')
export class NiqeModal extends LitElement {
  @property({ type: Boolean }) open: boolean = false
  @property({ type: Object }) variation: any = null

  static styles = css`
    :host {
      display: contents;
    }

    .backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(6px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 1.5rem;
      animation: fadeIn 0.15s ease-out;
    }

    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .modal {
      background: #141414;
      border: 1px solid #333;
      border-radius: 16px;
      width: 100%;
      max-width: 620px;
      max-height: 88vh;
      overflow-y: auto;
      box-shadow: 0 24px 64px rgba(0, 0, 0, 0.65);
      color: #e0e0e0;
      display: flex;
      flex-direction: column;
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1.4rem 1.75rem;
      border-bottom: 1px solid #262626;
    }

    .header-title-group {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .badge-pill {
      background: rgba(66, 133, 244, 0.15);
      color: #4285F4;
      border: 1px solid rgba(66, 133, 244, 0.35);
      font-size: 0.72rem;
      font-weight: 700;
      padding: 3px 9px;
      border-radius: 999px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    h2 {
      font-family: 'Manrope', sans-serif;
      font-size: 1.25rem;
      font-weight: 800;
      margin: 0;
      color: #fff;
    }

    .close-btn {
      background: transparent;
      border: 1px solid #333;
      color: #888;
      width: 32px;
      height: 32px;
      border-radius: 8px;
      font-size: 1.1rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s;
    }

    .close-btn:hover {
      color: #fff;
      border-color: #555;
      background: #222;
    }

    .modal-body {
      padding: 1.5rem 1.75rem;
      display: flex;
      flex-direction: column;
      gap: 1.35rem;
      font-size: 0.9rem;
      line-height: 1.55;
    }

    p {
      margin: 0;
      color: #bbb;
    }

    .section-heading {
      font-family: 'Manrope', sans-serif;
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #888;
      margin-bottom: 0.6rem;
    }

    .scale-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0.65rem;
    }

    .scale-card {
      background: #1c1c1c;
      border: 1px solid #2a2a2a;
      border-radius: 10px;
      padding: 0.8rem 0.95rem;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }

    .scale-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 700;
      font-size: 0.85rem;
    }

    .scale-desc {
      font-size: 0.78rem;
      color: #888;
      line-height: 1.35;
    }

    .good-green { color: #34a853; }
    .good-blue { color: #4285F4; }
    .warn-amber { color: #fbbc04; }
    .bad-red { color: #ea4335; }

    .variation-box {
      background: rgba(66, 133, 244, 0.07);
      border: 1px solid rgba(66, 133, 244, 0.28);
      border-radius: 12px;
      padding: 1rem 1.15rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    .variation-stats {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.6rem;
    }

    .stat-cell {
      background: #181818;
      border: 1px solid #2a2a2a;
      border-radius: 8px;
      padding: 0.55rem 0.75rem;
      text-align: center;
    }

    .stat-label {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #888;
      font-weight: 600;
    }

    .stat-val {
      font-family: 'Manrope', sans-serif;
      font-size: 1.15rem;
      font-weight: 800;
      color: #4285F4;
      margin-top: 0.15rem;
    }

    .frame-row {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .frame-chip {
      flex: 1;
      min-width: 72px;
      background: #181818;
      border: 1px solid #2a2a2a;
      border-radius: 6px;
      padding: 0.35rem 0.5rem;
      font-size: 0.75rem;
      display: flex;
      justify-content: space-between;
      color: #aaa;
    }

    .frame-chip strong {
      color: #fff;
    }

    .callout {
      background: #1b1b1b;
      border-left: 3px solid #4285F4;
      border-radius: 6px;
      padding: 0.75rem 1rem;
      font-size: 0.82rem;
      color: #aaa;
    }

    .callout strong {
      color: #fff;
    }
  `

  private close() {
    this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }))
  }

  private handleBackdropClick(e: MouseEvent) {
    if ((e.target as HTMLElement).classList.contains('backdrop')) {
      this.close()
    }
  }

  render() {
    if (!this.open) return html``

    const m = this.variation?.metrics
    const frameScores: number[] = m?.frame_scores || []

    return html`
      <div class="backdrop" @click=${this.handleBackdropClick}>
        <div class="modal" role="dialog" aria-modal="true" aria-label="NIQE Quality Metric Explanation">
          <div class="modal-header">
            <div class="header-title-group">
              <h2>NIQE Technical Quality Score</h2>
              <span class="badge-pill">Lower is Better</span>
            </div>
            <button class="close-btn" @click=${this.close} title="Close">✕</button>
          </div>

          <div class="modal-body">
            ${m ? html`
              <div class="variation-box">
                <div class="section-heading" style="margin-bottom: 0; color: #4285F4;">
                  Variation ${(this.variation.id ?? 0) + 1} — 5-Frame NIQE Breakdown
                </div>
                <div class="variation-stats">
                  <div class="stat-cell">
                    <div class="stat-label">Mean Score</div>
                    <div class="stat-val">${m.avg_score?.toFixed(2)}</div>
                  </div>
                  <div class="stat-cell">
                    <div class="stat-label">Best Frame (Min)</div>
                    <div class="stat-val" style="color: #34a853;">${m.min_score?.toFixed(2)}</div>
                  </div>
                  <div class="stat-cell">
                    <div class="stat-label">Softest Frame (Max)</div>
                    <div class="stat-val" style="color: #fbbc04;">${m.max_score?.toFixed(2)}</div>
                  </div>
                </div>
                ${frameScores.length > 0 ? html`
                  <div class="frame-row">
                    ${frameScores.map((s, idx) => html`
                      <div class="frame-chip">
                        <span>F${idx + 1}</span>
                        <strong>${s.toFixed(2)}</strong>
                      </div>
                    `)}
                  </div>
                ` : ''}
              </div>
            ` : ''}

            <div>
              <div class="section-heading">What is NIQE?</div>
              <p>
                <strong style="color:#fff;">NIQE (Natural Image Quality Evaluator)</strong> is an objective, no-reference ("blind") perceptual quality metric. Rather than requiring a ground-truth reference video or human opinion training labels, NIQE measures how closely a video frame's spatial texture statistics match a statistical model of pristine, undistorted natural images.
              </p>
            </div>

            <div>
              <div class="section-heading">How to Interpret Scores (Lower = Higher Perceptual Naturalness)</div>
              <div class="scale-grid">
                <div class="scale-card">
                  <div class="scale-top">
                    <span class="good-green">Excellent</span>
                    <span class="good-green">&lt; 3.5</span>
                  </div>
                  <div class="scale-desc">Crisp detail, natural micro-textures, minimal compression or synthesis artifacts.</div>
                </div>
                <div class="scale-card">
                  <div class="scale-top">
                    <span class="good-blue">Good</span>
                    <span class="good-blue">3.5 – 5.0</span>
                  </div>
                  <div class="scale-desc">Clean perceptual quality typical of natural 360p–720p generative video.</div>
                </div>
                <div class="scale-card">
                  <div class="scale-top">
                    <span class="warn-amber">Fair / Stylized</span>
                    <span class="warn-amber">5.0 – 6.5</span>
                  </div>
                  <div class="scale-desc">Noticeable motion blur, shallow depth-of-field bokeh, haze, or mild artifacts.</div>
                </div>
                <div class="scale-card">
                  <div class="scale-top">
                    <span class="bad-red">Degraded</span>
                    <span class="bad-red">&gt; 6.5</span>
                  </div>
                  <div class="scale-desc">Heavy blur, compression blocking, noise, or unnatural spatial textures.</div>
                </div>
              </div>
            </div>

            <div>
              <div class="section-heading">How Variations Studio Computes NIQE</div>
              <p>
                Once a video variation finishes rendering, the backend uses <code>ffmpeg</code> to sample <strong style="color:#fff;">5 evenly spaced frames</strong> across the clip's duration and evaluates each frame with <strong style="color:#fff;">PyIQA</strong> (<code>pyiqa</code> on PyTorch). The tile displays the mean NIQE score across all 5 sampled frames.
              </p>
            </div>

            <div class="callout">
              <strong>Creative Tip:</strong> Because NIQE rewards sharp, natural spatial textures, prompts requesting <em>soft-focus bokeh</em>, <em>misty haze</em>, or <em>fast shaky-cam motion blur</em> will naturally score higher than crisp studio macro shots. Use NIQE to compare technical sharpness across variations of a similar style.
            </div>
          </div>
        </div>
      </div>
    `
  }
}
