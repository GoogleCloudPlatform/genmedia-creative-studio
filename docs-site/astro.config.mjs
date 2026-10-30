// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import catppuccin from '@catppuccin/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://GoogleCloudPlatform.github.io',
	base: '/genmedia-creative-studio/',
	integrations: [
		starlight({
			title: 'GenMedia Creative Studio',
			favicon: '/favicon.ico',
			customCss: ['./src/styles/custom.css'],
			head: [
				{
					tag: 'script',
					content: `
						function initDiagramLightbox() {
							let dialog = document.querySelector('dialog.sl-image-lightbox');
							if (!dialog) {
								dialog = document.createElement('dialog');
								dialog.className = 'sl-image-lightbox';
								dialog.innerHTML = \`
									<div class="sl-lightbox-container">
										<div class="sl-lightbox-viewport">
											<img alt="" />
										</div>
										<div class="sl-lightbox-bar">
											<span class="sl-lightbox-caption"></span>
											<div class="sl-lightbox-actions">
												<button type="button" class="sl-lightbox-btn" data-action="zoom">1:1 Zoom</button>
												<button type="button" class="sl-lightbox-btn" data-action="close">Close (Esc)</button>
											</div>
										</div>
									</div>
								\`;
								document.body.appendChild(dialog);

								const viewport = dialog.querySelector('.sl-lightbox-viewport');
								const modalImg = viewport.querySelector('img');
								const zoomBtn = dialog.querySelector('[data-action="zoom"]');
								const closeBtn = dialog.querySelector('[data-action="close"]');

								function toggleZoom() {
									const zoomed = viewport.classList.toggle('is-zoomed');
									zoomBtn.textContent = zoomed ? 'Fit to Screen' : '1:1 Zoom';
								}

								modalImg.addEventListener('click', (e) => {
									e.stopPropagation();
									toggleZoom();
								});
								zoomBtn.addEventListener('click', (e) => {
									e.stopPropagation();
									toggleZoom();
								});
								closeBtn.addEventListener('click', () => dialog.close());
								dialog.addEventListener('click', (e) => {
									if (e.target === dialog || e.target.classList.contains('sl-lightbox-container')) {
										dialog.close();
									}
								});
							}

							const viewport = dialog.querySelector('.sl-lightbox-viewport');
							const modalImg = viewport.querySelector('img');
							const caption = dialog.querySelector('.sl-lightbox-caption');
							const zoomBtn = dialog.querySelector('[data-action="zoom"]');

							document.querySelectorAll('.sl-markdown-content img').forEach((img) => {
								if (img.dataset.lightboxBound === 'true') return;
								img.dataset.lightboxBound = 'true';
								img.title = img.title || 'Click to enlarge diagram';
								img.addEventListener('click', () => {
									viewport.classList.remove('is-zoomed');
									zoomBtn.textContent = '1:1 Zoom';
									modalImg.src = img.currentSrc || img.src;
									modalImg.alt = img.alt || '';
									caption.textContent = img.alt || 'Architecture Diagram (click image to toggle 1:1 zoom)';
									dialog.showModal();
								});
							});
						}
						document.addEventListener('DOMContentLoaded', initDiagramLightbox);
						document.addEventListener('astro:page-load', initDiagramLightbox);
					`,
				},
			],
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/GoogleCloudPlatform/genmedia-creative-studio' }],
			// Bright Catppuccin theme: Latte (light) forward, with Mocha for dark mode.
			plugins: [catppuccin({
				light: { flavor: 'latte', accent: 'blue' },
				dark: { flavor: 'mocha', accent: 'blue' },
			})],
			sidebar: [
				{
					label: 'Core Application',
					items: [
						{ label: 'Introduction', slug: 'core' },
						{ label: 'Using the Studio', slug: 'core/usage' },
						{ label: 'Architecture', slug: 'core/architecture' },
						{
							label: 'Foundation Models',
							items: [
								{ label: 'Overview', slug: 'core/foundation-models' },
								{ label: 'Gemini Omni', slug: 'core/foundation-models/gemini-omni' },
								{ label: 'Veo Video Generation', slug: 'core/foundation-models/veo' },
								{ label: 'Gemini Image (Nano Banana)', slug: 'core/foundation-models/nano-banana' },
								{ label: 'Lyria Music Generation', slug: 'core/foundation-models/lyria' },
								{ label: 'Gemini TTS', slug: 'core/foundation-models/gemini-tts' },
								{ label: 'Chirp 3 HD', slug: 'core/foundation-models/chirp-3hd' },
								{ label: 'Writers Workshop', slug: 'core/foundation-models/writers-workshop' },
							]
						},
						{
							label: 'Creative Workflows',
							items: [
								{ label: 'Overview', slug: 'core/workflows' },
								{ label: 'Storyboarder', slug: 'core/workflows/storyboarder' },
								{ label: 'Shop the Look', slug: 'core/workflows/shop-the-look' },
								{ label: 'Character Consistency', slug: 'core/workflows/character-consistency' },
								{ label: 'Interior Design', slug: 'core/workflows/interior-design' },
								{ label: 'Virtual Try-On (VTO)', slug: 'core/workflows/virtual-try-on' },
								{ label: 'Starter Pack', slug: 'core/workflows/starter-pack' },
								{ label: 'Motion Portraits', slug: 'core/workflows/motion-portraits' },
								{ label: 'Pixie Compositor', slug: 'core/workflows/pixie-compositor' },
								{ label: 'Labs & Experimental', slug: 'core/workflows/labs' },
							]
						},
						{
							label: 'Installation',
							items: [
								{ label: 'Local Setup', slug: 'core/installation/local_setup' },
								{ label: 'Deployment Guide', slug: 'core/installation/deploy' },
								{ label: 'GKE (Self-Service)', slug: 'core/installation/gke' },
								{ label: 'Terraform', slug: 'core/installation/terraform' },
								{ label: 'Environment Variables', slug: 'core/installation/environment_variables' },
                                                                { label: 'Cost Tracking Analytics', slug: 'core/installation/cost_tracking' },
							]
						},
						{ label: 'Developers Guide', slug: 'core/developers_guide' },
						{ label: 'FAQ', slug: 'core/faq' },
						{ label: 'Changelog & Notices', slug: 'core/changelog' },
					],
				},
				{
					label: 'AI Workflows & Demos',
					items: [
						{ label: 'Overview', slug: 'experiments/overview' },
						{
							label: 'Video Generation',
							items: [
								{ label: 'Veo Variations', slug: 'experiments/veo-variations' },
								{ label: 'Run Veo Run', slug: 'experiments/run-veo-run' },
								{ label: 'Countdown Workflow', slug: 'experiments/countdown-workflow' },
								{ label: 'Creative GenMedia Workflow', slug: 'experiments/creative-genmedia-workflow' },
								{ label: 'Veo Genetic Prompt Optimizer', slug: 'experiments/veo-genetic-prompt-optimizer' },
								{ label: 'Veo 3 Character Consistency', slug: 'experiments/veo3-character-consistency' },
								{ label: 'Veo 3 Item Consistency', slug: 'experiments/veo3-item-consistency' },
							]
						},
						{
							label: 'Image Generation',
							items: [
								{ label: 'Product Recontextualization', slug: 'experiments/imagen_product_recontext' },
								{ label: 'Virtual Try-On', slug: 'experiments/vto' },
								{ label: 'Brand Consistency', slug: 'experiments/brand_consistency' }
							]
						},
						{
							label: 'Audio & Voice',
							items: [
								{ label: 'Babel', slug: 'experiments/babel' },
							]
						}
					]
				},
				{
					label: 'Developer Tools',
					items: [
						{ label: 'Promptlandia', slug: 'experiments/promptlandia' },
						{ label: 'Agent Tools for Genmedia', slug: 'experiments/agent-tools' },
						{
							label: 'MCP GenMedia',
							items: [
								{ label: 'Overview', slug: 'experiments/mcp-genmedia' },
								{ label: 'Host on Cloud Run', slug: 'experiments/mcp-genmedia/host-on-cloud-run' },
								{
									label: 'Servers',
									items: [
										{ label: 'mcp-veo-go', slug: 'experiments/mcp-genmedia/mcp-veo-go' },
										{ label: 'mcp-imagen-go', slug: 'experiments/mcp-genmedia/mcp-imagen-go' },
										{ label: 'mcp-lyria-go', slug: 'experiments/mcp-genmedia/mcp-lyria-go' },
										{ label: 'mcp-chirp3-go', slug: 'experiments/mcp-genmedia/mcp-chirp3-go' },
										{ label: 'mcp-nanobanana-go', slug: 'experiments/mcp-genmedia/mcp-nanobanana-go' },
										{ label: 'mcp-gemini-go', slug: 'experiments/mcp-genmedia/mcp-gemini-go' },
										{ label: 'mcp-gemini-transcribe-go', slug: 'experiments/mcp-genmedia/mcp-gemini-transcribe-go' },
										{ label: 'mcp-omni-go', slug: 'experiments/mcp-genmedia/mcp-omni-go' },
										{ label: 'mcp-avtool-go', slug: 'experiments/mcp-genmedia/mcp-avtool-go' },
									]
								},
								{
									label: 'Skills',
									items: [{ autogenerate: { directory: 'experiments/mcp-genmedia/skills' } }]
								},
								{
									label: 'Sample Agents',
									items: [{ autogenerate: { directory: 'experiments/mcp-genmedia/agents' } }]
								}
							]
						}
					]
				},
			],
		}),
	],
});
