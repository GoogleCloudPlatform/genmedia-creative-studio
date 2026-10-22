import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'

@customElement('variation-tile')
export class VariationTile extends LitElement {
  @property({ type: Object }) data: any = null
  @property({ type: String }) apiBase: string = ''
  @state() private showC2PADetails: boolean = false

  static styles = css`
    :host { display: block; height: 100%; position: relative; }
    
    .tile {
      background-color: #121212;
      border-radius: 16px;
      overflow: hidden;
      height: 100%;
      display: flex;
      flex-direction: column;
      border: 1px solid #333;
      transition: border-color 0.3s, transform 0.2s;
    }

    .tile:hover { border-color: #444; transform: translateY(-2px); }

    .media-container {
      width: 100%;
      aspect-ratio: 16/9;
      background-color: #000;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }

    video { width: 100%; height: 100%; object-fit: cover; }

    .overlay {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
      color: #888;
      font-size: 0.85rem;
    }

    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid #333;
      border-top: 3px solid #4285F4;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

    .info-pane {
      padding: 1.2rem;
      display: flex;
      flex-direction: column;
      gap: 0.8rem;
      flex-grow: 1;
    }

    .prompt-text {
      font-size: 0.85rem;
      line-height: 1.4;
      color: #aaa;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .stats-row {
      display: flex;
      gap: 1rem;
      font-size: 0.75rem;
      color: #666;
      font-weight: 600;
      align-items: center;
    }

    .niqe-trigger {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      cursor: pointer;
      padding: 2px 6px;
      margin-left: -6px;
      border-radius: 6px;
      transition: background 0.15s, color 0.15s;
    }

    .niqe-trigger:hover {
      background: rgba(66, 133, 244, 0.12);
      color: #ccc;
    }

    .niqe-help-icon {
      font-size: 0.7rem;
      color: #4285F4;
      opacity: 0.85;
    }

    .meta-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: auto;
      padding-top: 0.5rem;
    }

    .badge {
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      color: #4285F4;
      background: rgba(66, 133, 244, 0.1);
      padding: 2px 8px;
      border-radius: 4px;
    }

    .c2pa-trigger {
      cursor: pointer;
      display: flex;
      align-items: center;
      opacity: 0.7;
      transition: opacity 0.2s;
    }
    .c2pa-trigger:hover { opacity: 1; }
    .c2pa-icon { width: 18px; height: 18px; }

    /* Flyover Details */
    .c2pa-flyover {
      position: absolute;
      bottom: 3rem;
      right: 1rem;
      width: 285px;
      background: #1a1a1a;
      border: 1px solid #3c4043;
      border-radius: 12px;
      padding: 0.9rem 1rem;
      box-shadow: 0 10px 28px rgba(0,0,0,0.65);
      z-index: 100;
      font-size: 0.72rem;
      color: #ccc;
      pointer-events: none;
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
    }

    .c2pa-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #333;
      padding-bottom: 0.4rem;
    }
    .c2pa-header { font-weight: 700; color: #4285F4; text-transform: uppercase; font-size: 0.65rem; letter-spacing: 0.03em; }
    .c2pa-pill {
      font-size: 0.6rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 1px 6px;
      border-radius: 4px;
      background: rgba(52, 168, 83, 0.15);
      color: #34A853;
      border: 1px solid rgba(52, 168, 83, 0.35);
    }
    .c2pa-meta-grid {
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
      font-size: 0.68rem;
      color: #aaa;
      background: rgba(255, 255, 255, 0.03);
      padding: 0.45rem 0.55rem;
      border-radius: 6px;
      border: 1px solid #2a2a2a;
    }
    .c2pa-meta-line { display: flex; justify-content: space-between; gap: 0.5rem; }
    .c2pa-meta-label { color: #777; font-weight: 600; flex-shrink: 0; }
    .c2pa-meta-val { color: #ddd; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .action-item { display: flex; gap: 0.4rem; line-height: 1.25; font-size: 0.7rem; }
    .action-bullet { color: #4285F4; }

    .error { color: #ea4335; font-size: 0.8rem; text-align: center; padding: 1rem; }
  `

  render() {
    if (!this.data) return html`<div class="tile empty"></div>`

    const isGenerating = this.data.status === 'generating' || this.data.status === 'analyzing'
    const isFailed = this.data.status === 'failed'
    const d = this.data

    return html`
      <div class="tile">
        <div class="media-container">
          ${isGenerating ? html`
            <div class="overlay">
              <div class="spinner"></div>
              <span>${d.status === 'generating' ? 'Animating...' : 'Evaluating...'}</span>
            </div>
          ` : isFailed ? html`
            <div class="error">
              <div>⚠️</div>
              <div>Failed to generate</div>
            </div>
          ` : html`
            <video controls loop src="${this.apiBase}/static/videos/${d.filename}"></video>
          `}
        </div>
        
        <div class="info-pane">
          <div class="prompt-text">${d.prompt}</div>
          
          ${d.metrics ? html`
            <div class="stats-row">
              <span
                class="niqe-trigger"
                title="Click to learn about NIQE & view 5-frame breakdown"
                @click=${() => this.dispatchEvent(new CustomEvent('open-niqe', { detail: d, bubbles: true, composed: true }))}
              >
                NIQE: <span style="color: #4285F4;">${d.metrics.avg_score.toFixed(2)}</span>
                <span class="niqe-help-icon">ⓘ</span>
              </span>
              <span>TIME: <span style="color: #4285F4;">${d.gen_time_sec ? d.gen_time_sec + 's' : '--'}</span></span>
            </div>
          ` : ''}

          <div class="meta-row">
            <span class="badge">Variation ${d.id + 1}</span>
            
            ${d.c2pa && d.c2pa.has_credentials !== false && d.c2pa.status !== 'Error' ? html`
              <div class="c2pa-trigger" 
                   @mouseenter=${() => this.showC2PADetails = true} 
                   @mouseleave=${() => this.showC2PADetails = false}>
                <img src="/c2pa-icon.png" class="c2pa-icon" alt="C2PA" />
              </div>
            ` : ''}
          </div>
        </div>

        ${this.showC2PADetails && d.c2pa ? html`
          <div class="c2pa-flyover">
            <div class="c2pa-header-row">
              <div class="c2pa-header">Credentio C2PA</div>
              <div style="display: flex; align-items: center; gap: 0.35rem;">
                ${d.c2pa.core_ms !== undefined ? html`<span style="font-size: 0.62rem; color: #888;">${d.c2pa.core_ms}ms</span>` : ''}
                <span class="c2pa-pill">${d.c2pa.badge || d.c2pa.status || 'SIGNED'}</span>
              </div>
            </div>
            <div style="font-size: 0.7rem; color: #bbb; font-weight: 600;">${d.c2pa.generator}</div>
            ${d.c2pa.signer?.subject || d.c2pa.validation ? html`
              <div class="c2pa-meta-grid">
                ${d.c2pa.signer?.subject ? html`
                  <div class="c2pa-meta-line">
                    <span class="c2pa-meta-label">Signer</span>
                    <span class="c2pa-meta-val">${d.c2pa.signer.subject}</span>
                  </div>
                ` : ''}
                ${d.c2pa.signer?.issuer ? html`
                  <div class="c2pa-meta-line">
                    <span class="c2pa-meta-label">Issuer</span>
                    <span class="c2pa-meta-val">${d.c2pa.signer.issuer}</span>
                  </div>
                ` : ''}
                ${d.c2pa.signer?.tsa_subject ? html`
                  <div class="c2pa-meta-line">
                    <span class="c2pa-meta-label">TSA</span>
                    <span class="c2pa-meta-val">${d.c2pa.signer.tsa_subject}</span>
                  </div>
                ` : ''}
                ${d.c2pa.validation ? html`
                  <div class="c2pa-meta-line">
                    <span class="c2pa-meta-label">Checks</span>
                    <span class="c2pa-meta-val" style="color: #34A853;">✓ ${d.c2pa.validation.checks_passed} passed (BMFF SHA-256)</span>
                  </div>
                ` : ''}
              </div>
            ` : ''}
            <div style="margin-top: 0.1rem; display: flex; flex-direction: column; gap: 0.25rem;">
              ${(d.c2pa.actions || []).map((a: any) => html`
                <div class="action-item">
                  <span class="action-bullet">•</span>
                  <span>${a.detail}</span>
                </div>
              `)}
            </div>
          </div>
        ` : ''}
      </div>
    `
  }
}
