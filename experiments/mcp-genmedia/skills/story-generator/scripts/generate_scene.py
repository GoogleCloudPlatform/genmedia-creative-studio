import argparse
import json
import subprocess
import os
import re
import glob
import math
import shutil
import tempfile
# Gemini Omni 1.2 clip length limits (seconds), see mcp-omni-go.
OMNI_MIN_SECONDS = 3
OMNI_MAX_SECONDS = 15

# Omni generates audio with the video. Narration and music are mixed in
# separately, so keep the clip's own track to ambient sound only.
OMNI_AUDIO_SUFFIX = ", ambient sound effects only, no speech, no dialogue, no narration, no music"

def resolve_in(out_dir, path):
    """Makes a path returned by an MCP server absolute (servers may return it relative to their cwd)."""
    return path if os.path.isabs(path) else os.path.join(out_dir, path)

def run_mcp(command, tool_name, arguments, cwd=None):
    """Calls one MCP tool over stdio.

    The MCP servers confine output_directory (and local input files) to their
    working directory, so pass cwd=<project dir> and project-relative paths.
    """
    env = os.environ.copy()
    env["GOOGLE_CLOUD_PROJECT"] = "genai-blackbelt-fishfooding"
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    # Keep stdin open until the response arrives: closing it right after the
    # request makes the server shut down and cancel long-running calls (such as
    # video generation) before they finish. stderr goes to a temp file so a full
    # pipe can never block the server.
    with tempfile.TemporaryFile(mode="w+") as err_file:
        p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err_file, text=True, env=env, cwd=cwd)
        out = ""
        try:
            p.stdin.write(json.dumps(req) + "\n")
            p.stdin.flush()
            for line in p.stdout:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                # Skip notifications (progress, logging); wait for our response.
                if isinstance(msg, dict) and msg.get("id") == 1 and ("result" in msg or "error" in msg):
                    out = line
                    break
        finally:
            try:
                p.stdin.close()
            except OSError:
                pass
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        err_file.seek(0)
        err = err_file.read()
    return out, err

def get_duration(file_path):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error parsing duration for {file_path}: {e}")
        return 0.0

def has_audio(file_path):
    cmd = f"ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 {file_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return len(result.stdout.strip()) > 0

def omni_server_command():
    """Returns the command for a server exposing omni_video_generation.

    mcp-omni-go is preferred; mcp-gemini-go (already needed for TTS) exposes the
    same tool, so it is used when mcp-omni-go is not on PATH.
    """
    for binary in ("mcp-omni-go", "mcp-gemini-go"):
        if shutil.which(binary):
            return [binary, "-t", "stdio"]
    return ["mcp-omni-go", "-t", "stdio"]

def omni_clip_seconds(voice_duration):
    """Picks the Omni clip length: the voiceover plus a small tail, within 3-15s."""
    return max(OMNI_MIN_SECONDS, min(OMNI_MAX_SECONDS, math.ceil(voice_duration + 0.25)))

def veo_clip_seconds(voice_duration):
    """Picks the Veo clip length (Veo only offers 4, 6 or 8 seconds)."""
    if voice_duration <= 4.2:
        return 4
    if voice_duration <= 6.2:
        return 6
    return 8

def generate_video_omni(args, out_dir, image_rel, voice_duration):
    """Image-to-video with Gemini Omni. Returns the local MP4 path or None.

    Runs the server from out_dir with relative paths: mcp-omni-go confines
    output_directory (and local input files) to its working directory.
    """
    seconds = omni_clip_seconds(voice_duration)
    print(f"Selecting Omni video generation duration: {seconds}s (based on voiceover length {voice_duration:.2f}s)")
    out, err = run_mcp(omni_server_command(), "omni_video_generation", {
        # One image without a task is the literal first frame.
        "images": [image_rel],
        "prompt": args.video + OMNI_AUDIO_SUFFIX,
        "duration_seconds": seconds,
        "aspect_ratio": "16:9",
        "resolution": args.resolution,
        "output_directory": "videos",
        "output_filename": f"scene{args.scene_id}_video.mp4",
    }, cwd=out_dir)
    try:
        res = json.loads(out)
        text = res['result']['content'][0]['text']
        match = re.search(r"Generated and saved \d+ video\(s\): (.*)", text)
        # Local paths come back first; ignore any gs:// copies.
        local = [p.strip() for p in match.group(1).split(", ") if not p.strip().startswith("gs://")]
        video_file = local[0]
        return resolve_in(out_dir, video_file)
    except Exception as e:
        print("Error parsing Video:", e, out, err)
        return None

def generate_video_veo(args, out_dir, image_file, bucket, s_id, voice_duration):
    """Image-to-video with Veo (fallback engine). Returns the local MP4 path or None."""
    # Veo reads the first frame from GCS, so upload the image first.
    print("Uploading image to GCS...")
    gcs_uri = f"gs://{bucket}/story_generator/scene{s_id}_image_{os.path.basename(image_file)}"
    subprocess.run(f"gcloud storage cp {image_file} {gcs_uri}", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    seconds = veo_clip_seconds(voice_duration)
    print(f"Dynamically selecting Veo video generation duration: {seconds}s (based on voiceover length {voice_duration:.2f}s)")
    out, err = run_mcp(["mcp-veo-go", "-t", "stdio"], "veo_i2v", {
        "image_uri": gcs_uri,
        "prompt": args.video,
        "model": "veo-3.1-lite-generate-001",
        "bucket": bucket,
        "output_directory": "videos",
        "duration": seconds,
        "aspect_ratio": "16:9",
        "generate_audio": True  # Enable native ambient audio generation
    }, cwd=out_dir)
    try:
        res = json.loads(out)
        text = res['result']['content'][0]['text']
        match = re.search(r"Successfully downloaded locally to '.*': (.*\.mp4)", text)
        return resolve_in(out_dir, match.group(1))
    except Exception as e:
        print("Error parsing Video:", e, out, err)
        return None

def main():
    parser = argparse.ArgumentParser(description="Generate a single media scene.")
    parser.add_argument("--scene_id", type=int, required=True)
    parser.add_argument("--narrator", type=str, required=True)
    parser.add_argument("--voice", type=str, default="Callirrhoe")
    # Short delivery style (Gemini 3.8 speechMetadata.style). Gender/accent come from --voice.
    parser.add_argument("--voice_prompt", type=str, default="soothing, gentle, unhurried")
    parser.add_argument("--music", type=str, required=True)
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--out_dir", type=str, required=True)
    parser.add_argument("--auto_speed_fit", type=bool, default=True)
    parser.add_argument("--video_engine", choices=["omni", "veo"], default="omni",
                        help="Video model: Gemini Omni 1.2 (default, 3-15s clips) or Veo 3.1 Lite (4/6/8s clips).")
    parser.add_argument("--resolution", default="720p",
                        help="Omni output resolution (360p, 720p, 1080p, 4k). Ignored for Veo.")
    
    args = parser.parse_args()
    
    out_dir = os.path.abspath(args.out_dir)
    bucket = "genai-blackbelt-fishfooding-assets"
    
    os.makedirs(f"{out_dir}/audio", exist_ok=True)
    os.makedirs(f"{out_dir}/images", exist_ok=True)
    os.makedirs(f"{out_dir}/videos", exist_ok=True)
    os.makedirs(f"{out_dir}/mixed", exist_ok=True)
    
    s_id = args.scene_id
    print(f"=== Processing Scene {s_id} ===")
    
    # 1. TTS
    print(f"Generating TTS for scene {s_id}...")
    out, err = run_mcp(["mcp-gemini-go", "-t", "stdio"], "gemini_audio_tts", {
        "text": args.narrator,
        "voice_name": args.voice,
        "prompt": args.voice_prompt,
        "output_directory": "audio",
        "output_filename_prefix": f"scene{s_id}_voice"
    }, cwd=out_dir)
    
    try:
        res = json.loads(out)
        text = res['result']['content'][0]['text']
        match = re.search(r"Audio saved to: (.*\.wav)", text)
        voice_file = resolve_in(out_dir, match.group(1))
        print("Voice file:", voice_file)
    except Exception as e:
        print("Error parsing TTS:", e, out)
        return

    # 2. Music
    print(f"Generating Music for scene {s_id}...")
    music_file = f"{out_dir}/audio/scene{s_id}_music.wav"
    music_prompt = args.music
    # Enforce strictly instrumental background scores, forbidding any vocals or synthetic voices
    music_prompt = f"{music_prompt}, strictly instrumental, no vocals, no voice, no singing, ambient background score"
        
    out, err = run_mcp(["mcp-lyria-go", "-t", "stdio"], "lyria_generate_music", {
        "prompt": music_prompt,
        "output_gcs_bucket": bucket,
        "local_path": "audio",
        "file_name": f"scene{s_id}_music.wav"
    }, cwd=out_dir)
    print("Music generation complete.")

    # 3. Image locally then upload (Nano Banana direct to GCS is sometimes flaky)
    print(f"Generating Image locally for scene {s_id}...")
    out, err = run_mcp(["mcp-nanobanana-go", "-t", "stdio"], "nanobanana_image_generation", {
        "prompt": args.image,
        "output_directory": "images",
        "aspect_ratio": "16:9"
    }, cwd=out_dir)
    try:
        res = json.loads(out)
        text = res['result']['content'][0]['text']
        match = re.search(r"Generated and saved 1 image\(s\): (.*\.png)", text)
        image_file = resolve_in(out_dir, match.group(1))
        print("Image file:", image_file)
    except Exception as e:
        print("Error parsing image:", e, out, err)
        return

    # Standardize image name for report compatibility
    subprocess.run(f'cp "{image_file}" "{out_dir}/images/scene{s_id}.png"', shell=True, check=True)

    # Size the video clip from the generated voice duration
    try:
        voice_duration = get_duration(voice_file)
    except Exception as e:
        print(f"Could not check voice duration before video generation, using default 6s: {e}")
        voice_duration = 6.0

    # 4. Video (i2v)
    print(f"Generating Video for scene {s_id} with {args.video_engine}...")
    if args.video_engine == "omni":
        video_file = generate_video_omni(args, out_dir, f"images/scene{s_id}.png", voice_duration)
    else:
        video_file = generate_video_veo(args, out_dir, image_file, bucket, s_id, voice_duration)
    if not video_file:
        return
    print("Video file:", video_file)

    # Standardize the raw clip name so the QC Room can find it
    std_video = f"{out_dir}/videos/scene{s_id}_video.mp4"
    if os.path.abspath(video_file) != os.path.abspath(std_video):
        shutil.move(video_file, std_video)
        video_file = std_video

    # 5. Advanced Mixing & Speed-Fitting
    print(f"Mixing Scene {s_id} with advanced compositing...")
    try:
        voice_duration = get_duration(voice_file)
        video_duration = get_duration(video_file)
        print(f"Scene durations: Voice = {voice_duration:.2f}s, Video = {video_duration:.2f}s")

        tempo = 1.0
        if args.auto_speed_fit and voice_duration > video_duration:
            target_duration = video_duration - 0.5
            if target_duration < 1.0:
                target_duration = video_duration
            tempo = voice_duration / target_duration
            # Clamp tempo: if it exceeds 1.25x, drop back to 1.0x (fully natural voice) and loop the video
            if tempo > 1.25:
                print(f"Notice: Required speed-up ({tempo:.2f}x) exceeds natural threshold (1.25x). Keeping voiceover at 1.00x and looping video.")
                tempo = 1.0
            if tempo < 1.0:
                tempo = 1.0
            if tempo > 1.0:
                print(f"Audio speed-fitting applied: tempo = {tempo:.2f}x")

        # Determine if voiceover needs speed-fitting filter
        voice_filter = "[1:a]volume=1.5[vo]"
        if tempo > 1.0:
            voice_filter = f"[1:a]atempo={tempo:.2f},volume=1.5[vo]"

        out_mix = f"{out_dir}/mixed/scene{s_id}_final.mp4"
        
        # Calculate the precise output duration of the scene based on voice and tempo
        out_duration = voice_duration / tempo
        print(f"Target mixed scene duration: {out_duration:.2f}s")
        
        # Pre-flight check for native video ambient audio
        video_has_audio = has_audio(video_file)
        print(f"Video has native ambient audio track: {video_has_audio}")

        if video_has_audio:
            # Three-track mixing: Ambient Video (ducked) + Voiceover (speed-fitted) + Music (ducked)
            # CRITICAL: [vo] must be the first input to amix when duration=first so that the stream ends when voiceover ends
            filter_complex = (
                f"[0:a]volume=0.25[bgv]; "
                f"{voice_filter}; "
                f"[2:a]volume=0.15[bgm]; "
                f"[vo][bgv][bgm]amix=inputs=3:duration=first:dropout_transition=0[aout]"
            )
        else:
            # Fallback mixing: Voiceover (speed-fitted) + Background Music (ducked)
            filter_complex = (
                f"{voice_filter}; "
                f"[2:a]volume=0.15[bgm]; "
                f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )

        cmd = (
            f'ffmpeg -y -stream_loop -1 -i "{video_file}" -i "{voice_file}" -i "{music_file}" '
            f'-filter_complex "{filter_complex}" '
            f'-map 0:v -map "[aout]" -t {out_duration:.3f} -c:v libx264 -preset fast -pix_fmt yuv420p -c:a aac -ar 44100 "{out_mix}"'
        )
        
        print("Running mixing command...")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print("ffmpeg mixing failed, trying fallback to voice and music only without stream-looping...")
            # Emergency Fallback: Replace entirely without relying on video's audio map
            cmd_fallback = (
                f'ffmpeg -y -i "{video_file}" -i "{voice_file}" -i "{music_file}" '
                f'-filter_complex "{voice_filter}; [2:a]volume=0.15[bgm]; [vo][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]" '
                f'-map 0:v -map "[aout]" -t {out_duration:.3f} -c:v copy -c:a aac -ar 44100 "{out_mix}"'
            )
            subprocess.run(cmd_fallback, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        print(f"Scene {s_id} complete! Mixed file: {out_mix}")
    except Exception as e:
        print("Error during advanced mixing:", e)

if __name__ == "__main__":
    main()
