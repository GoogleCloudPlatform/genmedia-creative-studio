import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'

const PRESETS = [
  {
    id: 'cola',
    label: 'Cola',
    image: '/samples/brit_cola.webp',
    prompt: 'changes to whimsical fairy like environment, a vibrant, whimsical explosion of sparkling bubbles, floating lime slices, and ethereal botanical shapes erupts around the can. The soda begins to levitate and spin slowly in a weightless, dreamlike space filled with glowing particles and soft-focus garden greenery'
  },
  {
    id: 'chair',
    label: 'Chair',
    image: '/samples/velvet_chair.webp',
    prompt: 'The environment rapidly dissolves into a surreal, neon-drenched cyberpunk lounge. Holographic rain begins to fall around the chair, illuminating it with pulsing magenta and cyan light. The velvet fabric seems to breathe and shift slightly as glowing digital data streams swirl in the air, transforming the room into a high-tech, atmospheric sanctuary.'
  },
  {
    id: 'sneaker',
    label: 'Sneaker',
    image: '/samples/neon_sneaker.webp',
    prompt: 'The puddle beneath the sneaker suddenly bursts into a dynamic portal of swirling liquid gold. The shoe is propelled upward as ribbons of molten, glowing metal wrap around the sole, solidifying into an intricate, gravity-defying sculpture. The asphalt shatters into floating, zero-gravity debris, backlit by intense, dramatic rim lighting in a void-like space.'
  }
];

const VIDEO_MODELS = [
  {
    id: 'gemini-omni-1.1-flash-preview',
    label: 'Gemini Omni 1.1 Flash (360p)',
    badge: 'Fast · ~25s'
  },
  {
    id: 'veo-3.1-lite-generate-001',
    label: 'Veo 3.1 Lite (720p)',
    badge: 'HD · ~55s'
  }
];

@customElement('concept-sidebar')
export class ConceptSidebar extends LitElement {
  @state() private prompt: string = ''
  @state() private variations: number = 4
  @state() private aspectRatio: string = '16:9'
  @state() private videoModel: string = 'gemini-omni-1.1-flash-preview'
  @state() private imagePreview: string | null = null
  @state() private selectedFile: File | null = null
  @state() private activePresetIndex: number | null = null

  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      background-color: #121212;
      padding: 2rem;
      gap: 2rem;
      border-right: 1px solid #333;
      height: 100vh;
      box-sizing: border-box;
      overflow-y: auto;
    }

    .section-title {
      font-family: 'Manrope', sans-serif;
      font-size: 0.9rem;
      font-weight: 700;
      color: #888;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }

    .section-title-left {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .clear-btn {
      color: #666;
      font-size: 0.75rem;
      text-transform: none;
      cursor: pointer;
      transition: color 0.2s;
    }

    .clear-btn:hover {
      color: #ea4335;
    }

    .upload-zone {
      width: 100%;
      aspect-ratio: 16/9;
      background-color: #1e1e1e;
      border: 2px dashed #333;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      overflow: hidden;
      transition: border-color 0.2s;
    }

    .upload-zone:hover { border-color: #4285F4; }
    .upload-zone img { width: 100%; height: 100%; object-fit: cover; }

    .input-group { display: flex; flex-direction: column; gap: 0.8rem; }

    textarea {
      width: 100%;
      height: 120px;
      background-color: #1e1e1e;
      border: 1px solid #333;
      border-radius: 8px;
      color: white;
      padding: 1rem;
      font-family: 'Inter', sans-serif;
      font-size: 0.95rem;
      resize: none;
      box-sizing: border-box;
    }

    .preset-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.8rem;
      margin-bottom: 0.5rem;
    }

    .preset-card {
      background: #1e1e1e;
      border: 2px solid transparent;
      border-radius: 8px;
      padding: 0.4rem;
      cursor: pointer;
      transition: transform 0.2s ease, border-color 0.2s ease;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.4rem;
    }

    .preset-card:hover {
      transform: scale(1.05);
      border-color: #333;
    }

    .preset-card.active {
      border-color: #4285F4;
    }

    .preset-card img {
      width: 100%;
      aspect-ratio: 16/9;
      object-fit: cover;
      border-radius: 4px;
    }

    .preset-card span {
      font-family: 'Inter', sans-serif;
      font-size: 0.75rem;
      color: #aaa;
      font-weight: 600;
    }

    .preset-card.active span {
      color: #4285F4;
    }

    .slider-row { display: flex; justify-content: space-between; align-items: center; }
    .val-badge { color: #4285F4; font-weight: 700; }

    input[type="range"] {
      width: 100%;
      accent-color: #4285F4;
      background: #333;
      height: 4px;
      border-radius: 2px;
      appearance: none;
    }

    .toggle-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      background: #1e1e1e;
      border-radius: 8px;
      padding: 4px;
    }

    .toggle-btn {
      padding: 0.6rem;
      text-align: center;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.85rem;
      font-weight: 600;
      transition: all 0.2s;
    }

    .toggle-btn.active { background: #333; color: #4285F4; border: 1px solid #444; }

    .model-select {
      width: 100%;
      background-color: #1e1e1e;
      color: #fff;
      border: 1px solid #333;
      border-radius: 8px;
      padding: 0.7rem 0.9rem;
      font-family: 'Inter', sans-serif;
      font-size: 0.88rem;
      font-weight: 600;
      cursor: pointer;
      outline: none;
      transition: border-color 0.2s;
    }

    .model-select:hover, .model-select:focus {
      border-color: #4285F4;
    }

    .generate-btn {
      margin-top: 1rem;
      padding: 1rem;
      background: #4285F4;
      color: white;
      border: none;
      border-radius: 12px;
      font-weight: 700;
      font-size: 1rem;
      cursor: pointer;
      transition: transform 0.1s, background 0.2s;
    }

    .generate-btn:hover { background: #3367d6; }
    .generate-btn:active { transform: scale(0.98); }
    .generate-btn:disabled { background: #333; color: #666; cursor: not-allowed; }
  `

  firstUpdated() {
    // Load the first preset by default
    this.applyPreset(0);
  }

  async applyPreset(index: number) {
    this.activePresetIndex = index;
    const preset = PRESETS[index];
    
    // Set prompt
    this.prompt = preset.prompt;
    
    // Fetch image and convert to File object to mimic upload behavior
    try {
      const response = await fetch(preset.image);
      const blob = await response.blob();
      const file = new File([blob], `preset_${preset.id}.webp`, { type: 'image/webp' });
      this.selectedFile = file;
      this.imagePreview = URL.createObjectURL(file);
    } catch (e) {
      console.error("Failed to load preset image", e);
    }
  }

  clearInputs() {
    this.prompt = '';
    this.imagePreview = null;
    this.selectedFile = null;
    this.activePresetIndex = null;
  }

  handleFile(e: any) {
    const file = e.target.files[0]
    if (file) {
      this.activePresetIndex = null; // Clear preset selection on manual upload
      this.selectedFile = file
      this.imagePreview = URL.createObjectURL(file)
    }
  }

  emitGenerate() {
    this.dispatchEvent(new CustomEvent('generate', {
      detail: {
        prompt: this.prompt,
        count: this.variations,
        aspectRatio: this.aspectRatio,
        model: this.videoModel,
        image: this.selectedFile
      }
    }))
  }

  render() {
    const activeModel = VIDEO_MODELS.find(m => m.id === this.videoModel) || VIDEO_MODELS[0];
    return html`
      <div class="input-group">
        <div class="section-title">
          <div class="section-title-left">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4285F4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: -2px;">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <circle cx="8.5" cy="8.5" r="1.5"></circle>
              <polyline points="21 15 16 10 5 21"></polyline>
            </svg>
            Product Image
          </div>
          ${this.imagePreview || this.prompt ? html`<span class="clear-btn" @click=${this.clearInputs}>Clear</span>` : ''}
        </div>
        <label class="upload-zone">
          <input type="file" hidden @change=${this.handleFile} accept="image/*" />
          ${this.imagePreview ? html`<img src=${this.imagePreview} />` : html`<span>Click to upload</span>`}
        </label>
      </div>

      <div class="input-group">
        <div class="section-title">Quick Presets</div>
        <div class="preset-grid">
          ${PRESETS.map((preset, index) => html`
            <div 
              class="preset-card ${this.activePresetIndex === index ? 'active' : ''}"
              @click=${() => this.applyPreset(index)}
            >
              <img src=${preset.image} alt=${preset.label} />
              <span>${preset.label}</span>
            </div>
          `)}
        </div>
      </div>

      <div class="input-group">
        <div class="section-title">Base Concept</div>
        <textarea .value=${this.prompt} @input=${(e: any) => {
          this.prompt = e.target.value;
          this.activePresetIndex = null; // Typing breaks the strict preset definition
        }}></textarea>
      </div>

      <div class="input-group">
        <div class="slider-row">
          <div class="section-title">Video Model</div>
          <span class="val-badge" style="font-size: 0.75rem;">${activeModel.badge}</span>
        </div>
        <select
          class="model-select"
          .value=${this.videoModel}
          @change=${(e: any) => this.videoModel = e.target.value}
        >
          ${VIDEO_MODELS.map(m => html`
            <option value=${m.id} ?selected=${this.videoModel === m.id}>${m.label}</option>
          `)}
        </select>
      </div>

      <div class="input-group">
        <div class="slider-row">
          <div class="section-title">Variations</div>
          <span class="val-badge">${this.variations}</span>
        </div>
        <input type="range" min="1" max="10" .value=${this.variations} @input=${(e: any) => this.variations = parseInt(e.target.value)} />
      </div>

      <div class="input-group">
        <div class="section-title">Aspect Ratio</div>
        <div class="toggle-row">
          <div class="toggle-btn ${this.aspectRatio === '16:9' ? 'active' : ''}" @click=${() => this.aspectRatio = '16:9'}>16:9</div>
          <div class="toggle-btn ${this.aspectRatio === '9:16' ? 'active' : ''}" @click=${() => this.aspectRatio = '9:16'}>9:16</div>
        </div>
      </div>

      <button class="generate-btn" @click=${this.emitGenerate}>Generate</button>
    `
  }
}
