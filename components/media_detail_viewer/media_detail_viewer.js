import { LitElement, css, html } from "https://cdn.jsdelivr.net/npm/lit/+esm";
import { SvgIcon } from "../svg_icon/svg_icon.js";
import "../download_button/download_button.js"; // Import the download button component
import "../convert_to_gif_button/convert_to_gif_button.js";

class MediaDetailViewer extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      --mdc-theme-primary: #1976d2;
    }
    .container {
      display: flex;
      flex-direction: row;
      gap: 24px;
    }
    .left-column {
      flex: 3;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .right-column {
      flex: 2;
      display: flex;
      flex-direction: column;
      gap: 16px;
      max-height: 80vh; /* Allow metadata to scroll */
      overflow-y: auto;
    }
    .main-asset {
      position: relative; /* For carousel buttons */
    }
    .main-asset img,
    .main-asset video {
      width: 100%;
      max-height: 60vh;
      object-fit: contain;
      border-radius: 8px;
    }
    .carousel-btn {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      background-color: rgba(0, 0, 0, 0.5);
      color: white;
      border: none;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      cursor: pointer;
      font-size: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .carousel-btn:hover {
      background-color: rgba(0, 0, 0, 0.8);
    }
    .prev-btn {
      left: 10px;
    }
    .next-btn {
      right: 10px;
    }
    .sources {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .sources img {
      width: 100px;
      height: 100px;
      object-fit: cover;
      border-radius: 4px;
      border: 1px solid var(--mesop-outline-variant-color);
    }
    h3 {
      margin: 0 0 8px 0;
      font-size: 1.2rem;
      font-weight: 500;
    }
    .metadata-item {
      display: flex;
      flex-direction: column;
      margin-bottom: 8px;
    }
    .metadata-key {
      font-weight: bold;
      font-size: 0.9rem;
      color: var(--mesop-on-surface-variant-color);
    }
    .metadata-value {
      font-size: 1rem;
      white-space: pre-wrap; /* Allow wrapping for long prompts */
      word-wrap: break-word;
    }
    .actions {
      display: flex;
      gap: 12px;
      margin-top: 16px;
    }
    .tabs {
      display: flex;
      border-bottom: 1px solid var(--mesop-outline-variant-color);
      margin-bottom: 16px;
    }
    .tab {
      padding: 8px 16px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
    }
    .tab[active] {
      border-bottom-color: var(--mesop-primary-color);
      font-weight: bold;
    }
    .raw-json {
      background-color: var(--mesop-surface-container-lowest-color);
      border-radius: 8px;
      padding: 16px;
      font-family: monospace;
      white-space: pre-wrap;
      word-wrap: break-word;
      font-size: 0.9rem;
    }
  `;

  static get properties() {
    return {
      mediaType: { type: String },
      primaryUrlsJson: { type: String },
      sourceUrlsJson: { type: String },
      metadataJson: { type: String },
      rawMetadataJson: { type: String },
      id: { type: String },
      editClickEvent: { type: String },
      veoClickEvent: { type: String },
      omniClickEvent: { type: String },
      extendClickEvent: { type: String },
      _currentIndex: { state: true },
      _activeTab: { state: true },
    };
  }

  constructor() {
    super();
    this.mediaType = "";
    this.primaryUrlsJson = "[]";
    this.sourceUrlsJson = "[]";
    this.metadataJson = "{}";
    this.rawMetadataJson = "{}";
    this.id = "";
    this.editClickEvent = "";
    this.veoClickEvent = "";
    this.omniClickEvent = "";
    this.extendClickEvent = "";
    this._currentIndex = 0;
    this._activeTab = "details";
  }

  _navigate(direction) {
    const urls = JSON.parse(this.primaryUrlsJson);
    const newIndex = this._currentIndex + direction;
    if (newIndex >= 0 && newIndex < urls.length) {
      this._currentIndex = newIndex;
    }
  }

  _dispatch(eventName, data) {
    if (!eventName) return;
    this.dispatchEvent(new MesopEvent(eventName, data));
  }

  _handleGifConversion(event) {
    if (event.detail.error)
      console.error('Conversion failed:', event.detail.error);

    const container = this.shadowRoot.getElementById('gif-container');

    const header = document.createElement('h5');
    header.textContent = 'Converted GIF';

    container.appendChild(header);

    const gifViewer = document.createElement('img');
    gifViewer.src = event.detail.url;
    gifViewer.id = 'converted-gif-viewer';
    gifViewer.style.width="100%";
    gifViewer.style.maxWidth="480px";
    gifViewer.style.borderRadius=8;

    container.appendChild(gifViewer);
  }

  renderPrimaryAsset() {
    const urls = JSON.parse(this.primaryUrlsJson);
    if (urls.length === 0) return html``;

    const currentUrl = urls[this._currentIndex];

    let assetHtml;
    switch (this.mediaType) {
      case "image":
        assetHtml = html`<img .src=${currentUrl} />`;
        break;
      case "video":
        assetHtml = html`<video .src=${currentUrl} controls autoplay></video>`;
        break;
      case "audio":
        assetHtml = html`<audio .src=${currentUrl} controls autoplay></audio>`;
        break;
      default:
        assetHtml = html`<p>Unknown or unsupported media type.</p>`;
    }

    const showButtons = urls.length > 1;

    return html`
      ${assetHtml}
      ${showButtons
        ? html`
            <button
              class="carousel-btn prev-btn"
              @click=${() => this._navigate(-1)}
              ?disabled=${this._currentIndex === 0}
            >
              &#x2039;
            </button>
            <button
              class="carousel-btn next-btn"
              @click=${() => this._navigate(1)}
              ?disabled=${this._currentIndex === urls.length - 1}
            >
              &#x203A;
            </button>
          `
        : ""}
    `;
  }

  renderSourceImages() {
    try {
      const sourceUrls = JSON.parse(this.sourceUrlsJson);
      if (sourceUrls.length === 0) return html``;

      return html`
        <h3>Sources</h3>
        <div class="sources">
          ${sourceUrls.map((url) => url.endsWith(".mp4") ? html`<video width="160" height="120" .src=${url} controls autoplay></video>` : html`<img .src=${url} />`)}
        </div>
      `;
    } catch (e) {
      return html`${e}`;
    }
  }

  renderMetadata() {
    try {
      const metadata = JSON.parse(this.metadataJson);
      return Object.entries(metadata).map(([key, value]) => {
        console.log("key:", key, "value:", value, "typeof value:", typeof value);
        let formattedValue = value;
        if (key === 'Generation Time (s)' && value !== null && !isNaN(parseFloat(value))) {
          console.log("is number:", !isNaN(parseFloat(value)));
          formattedValue = Math.round(value * 100) / 100 + ' seconds';
        } else if (key === 'Timestamp' && value) {
          const date = new Date(value);
          if (!isNaN(date)) {
            formattedValue = date.toLocaleString();
          }
        }
        return html`
          <div class="metadata-item">
            <span class="metadata-key">${key}</span>
            <span class="metadata-value">${formattedValue}</span>
          </div>
        `;
      });
    } catch (e) {
      return html`<p>Could not parse metadata.</p>`;
    }
  }

  renderRawMetadata() {
    try {
      const rawMetadata = JSON.parse(this.rawMetadataJson);
      return html`
        <div class="metadata-item">
          <span class="metadata-key">Firestore Document ID</span>
          <span class="metadata-value">${this.id}</span>
        </div>
        <pre class="raw-json"><code>${JSON.stringify(rawMetadata, null, 2)}</code></pre>
      `;
    } catch (e) {
      return html`<p>Could not parse raw metadata.</p>`;
    }
  }

  renderActions() {
    const urls = JSON.parse(this.primaryUrlsJson);
    if (urls.length === 0) return html``;
    const currentUrl = urls[this._currentIndex]; // This is the proxy URL, e.g., /media/bucket/object.png

    // Correctly convert the proxy URL back to a GCS URI for backend functions
    const isProxyUrl = currentUrl.startsWith("/media/");
    const gcsPath = isProxyUrl ? currentUrl.substring(7) : new URL(currentUrl).pathname.substring(1);
    const gcsUri = `gs://${gcsPath}`;

    const isImage = this.mediaType === 'image';
    const isVideo = this.mediaType === 'video';

    const handleCopyLink = () => {
      if (!navigator.clipboard) {
        alert("Copy to clipboard is only available on secure (HTTPS) sites.");
        return;
      }
      const url = new URL(window.location.href);
      url.searchParams.set("media_id", this.id);
      navigator.clipboard.writeText(url.href).then(() => {
        // Optional: show a temporary success message
        const copyButton = this.shadowRoot.querySelector("#copy-link-btn");
        if (copyButton) {
          const originalText = copyButton.textContent;
          copyButton.textContent = "Copied!";
          setTimeout(() => {
            copyButton.textContent = originalText;
          }, 2000);
        }
      });
    };

    return html`
      <div class="actions">
        <download-button .url=${gcsUri} .filename=${gcsPath.split("/").pop()}></download-button>
        ${isImage ? html`<mwc-button outlined @click=${() => this._dispatch(this.editClickEvent, {url: currentUrl})}><svg-icon slot="icon" .iconName=${'edit'}></svg-icon>Edit</mwc-button>` : ""}
        ${isImage ? html`<mwc-button outlined @click=${() => this._dispatch(this.veoClickEvent, {url: currentUrl})}><svg-icon slot="icon" .iconName=${'movie_filter'}></svg-icon>Veo</mwc-button>` : ""}
        ${isImage ? html`<mwc-button outlined @click=${() => this._dispatch(this.omniClickEvent, {url: currentUrl})}><svg-icon slot="icon" .iconName=${'spark'}></svg-icon>Omni</mwc-button>` : ""}
        ${isVideo ? html`<mwc-button outlined @click=${() => this._dispatch(this.extendClickEvent, {url: currentUrl})}><svg-icon slot="icon" .iconName=${'movie_filter'}></svg-icon>Extend</mwc-button>` : ""}
        <mwc-button id="copy-link-btn" outlined @click=${handleCopyLink}><svg-icon slot="icon" .iconName=${'link'}></svg-icon>Copy Link</mwc-button>
        ${this.mediaType === 'video' ? html`<convert-to-gif-button .url=${gcsUri} @conversion-complete=${this._handleGifConversion}></convert-to-gif-button>` : ""}
      </div>
    `;
  }

  render() {
    return html`
      <div class="container">
        <div class="left-column">
          <div class="main-asset">${this.renderPrimaryAsset()}</div>
          ${this.renderActions()}
          ${this.renderSourceImages()}
          <div id='gif-container' display="flex" flex-direction="column" align-items="center" gap="10"></div>
        </div>
        <div class="right-column">
          <div class="tabs">
            <div class="tab" ?active=${this._activeTab === 'details'} @click=${() => { this._activeTab = 'details' }}>Details</div>
            <div class="tab" ?active=${this._activeTab === 'raw'} @click=${() => { this._activeTab = 'raw' }}>Raw</div>
          </div>
          ${this._activeTab === 'details' ? this.renderMetadata() : this.renderRawMetadata()}
        </div>
      </div>
    `;
  }
}

customElements.define("media-detail-viewer", MediaDetailViewer);
