import argparse
import json
import os
import shutil

html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - Making Of</title>
  <link rel="stylesheet" href="index.css">
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p class="subtitle">Making-Of Production Overview</p>
    <p class="logline">{logline}</p>
    <div class="hero-video-container">
      <div class="hero-label">The Final Masterpiece</div>
      <video controls preload="auto">
        <source src="../{final_video}" type="video/mp4">
        Your browser does not support the video tag.
      </video>
    </div>
  </header>
  <main>
    <section id="pitch">
      <h2>The Pitch & Design</h2>
      <div class="card character-sheet">
        <div class="character-details">
          <h3>The Protagonist</h3>
          <p style="color: var(--md-sys-color-on-surface); font-size: 1.15rem; line-height: 1.6;">{character_details}</p>
        </div>
        <div class="character-image" style="border-radius: var(--border-radius-md); overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.3); max-width: 450px; flex: 1; border: 1px solid rgba(255,255,255,0.08);">
          <img src="../images/{character_image}" alt="Character Sheet" style="width: 100%; display: block; object-fit: cover;">
        </div>
      </div>
    </section>
    <section id="pipeline-architecture">
      <h2>Double-Engine Production Pipeline Architecture</h2>
      <p class="section-desc">
        Visual flowchart mapping of the automated Writers Room co-creation, dynamic scene composition, multi-track audio mixing, and Editors Quality Control Room audit.
      </p>
      <div class="card architecture-card" style="text-align: center; padding: 24px; display: flex; justify-content: center; align-items: center; border: 1px solid rgba(255,255,255,0.08);">
        <img src="pipeline_diagram.webp" alt="Double-Engine Pipeline Flowchart" style="max-width: 100%; height: auto; border-radius: var(--border-radius-md); box-shadow: 0 8px 24px rgba(0,0,0,0.3);">
      </div>
    </section>
    <section id="dailys">
      <h2>The Dailys (Scene-by-Scene)</h2>
      <p class="section-desc">
        Each scene was generated using Nano Banana (Images), Gemini Omni (Video), Gemini TTS (Voice), and Lyria (Music).
      </p>
      <div class="dailys-list">
{scenes_html}
      </div>
    </section>
  </main>
  <footer><p>Produced with Antigravity CLI • Google Cloud MCP Servers for Genmedia</p></footer>
</body>
</html>
"""

scene_template = """        <div class="scene-card card">
          <div class="scene-media-group">
            <div class="scene-media-item">
              <div class="media-label">Base Frame</div>
              <div class="scene-media">
                <img src="../images/{image}" alt="Scene {id} Base Frame">
              </div>
            </div>
            <div class="scene-media-item">
              <div class="media-label">Rendered & Mixed Clip</div>
              <div class="scene-media">
                <video controls preload="metadata">
                  <source src="../mixed/scene{id}_final.mp4" type="video/mp4">
                  Your browser does not support the video tag.
                </video>
              </div>
            </div>
          </div>
          <div class="scene-info">
            <div class="scene-number">Scene {id}: {title}</div>
            <div class="scene-narrator">"{narrator}"</div>
            <div class="scene-details">
              <div class="detail-tag"><span class="tag-title">Visual:</span> {image_prompt}</div>
              <div class="detail-tag"><span class="tag-title">Motion:</span> {motion_prompt}</div>
              <div class="detail-tag"><span class="tag-title">Music:</span> {music_prompt}</div>
            </div>
          </div>
        </div>"""

def main():
    parser = argparse.ArgumentParser(description="Generate an HTML report for a story project.")
    parser.add_argument("--project_dir", type=str, required=True, help="Target project directory")
    parser.add_argument("--title", type=str, required=True, help="Title of the storybook")
    parser.add_argument("--logline", type=str, required=True, help="Brief logline summary")
    parser.add_argument("--character_details", type=str, required=True, help="Character description details")
    parser.add_argument("--character_image", type=str, required=True, help="Filename of the main character image (under images/)")
    parser.add_argument("--scenes_json", type=str, required=True, help="Path to JSON file containing scenes list metadata")
    
    args = parser.parse_args()

    # Load scenes data
    with open(args.scenes_json, 'r') as f:
        scenes_data = json.load(f)

    # Find final video
    final_video = "final_story.mp4"
    for file in os.listdir(args.project_dir):
        if file.endswith("final.mp4") or file == "final_story.mp4":
            final_video = file
            break

    # Build the scene HTML using our standard template structure
    formatted_scenes = []
    for s in scenes_data:
        # Provide defaults for missing parameters to remain backwards compatible
        scene_id = s.get("id", 1)
        scene_title = s.get("title", f"Scene {scene_id}")
        formatted_scenes.append(scene_template.format(
            id=scene_id,
            title=scene_title,
            image=s.get("image", f"scene{scene_id}.png"),
            narrator=s.get("narrator", ""),
            image_prompt=s.get("image_prompt", s.get("prompt", "")),
            motion_prompt=s.get("motion_prompt", "Subtle motion"),
            music_prompt=s.get("music_prompt", "Whimsical instrumental")
        ))
        
    scenes_html = "\n".join(formatted_scenes)

    final_html = html_template.format(
        title=args.title,
        logline=args.logline,
        final_video=final_video,
        character_details=args.character_details,
        character_image=args.character_image,
        scenes_html=scenes_html
    )

    report_dir = os.path.join(args.project_dir, "report")
    os.makedirs(report_dir, exist_ok=True)

    # Copy styles and fonts from the skill assets directory
    skill_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets_src = os.path.join(skill_root_dir, "assets")
    
    # Copy index.css if it exists in skill assets
    css_src_path = os.path.join(assets_src, "index.css")
    if os.path.exists(css_src_path):
        print(f"Copying CSS from skill assets: {css_src_path}")
        shutil.copy(css_src_path, os.path.join(report_dir, "index.css"))
    else:
        print("Warning: CSS file not found in skill assets.")

    # Copy fonts from skill assets
    fonts_src = os.path.join(assets_src, "fonts")
    fonts_dest = os.path.join(report_dir, "fonts")
    if os.path.exists(fonts_src):
        print(f"Copying Fonts from skill assets: {fonts_src}")
        shutil.copytree(fonts_src, fonts_dest, dirs_exist_ok=True)
    else:
        print("Warning: Fonts not found in skill assets.")

    output_html_path = os.path.join(report_dir, 'index.html')
    with open(output_html_path, 'w') as f:
        f.write(final_html)

    print(f"Report generated successfully at: {output_html_path}")

if __name__ == "__main__":
    main()
