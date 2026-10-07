import argparse
import json
import subprocess
import os
import re
import glob

def run_mcp(command, tool_name, arguments):
    env = os.environ.copy()
    env["GOOGLE_CLOUD_PROJECT"] = "genai-blackbelt-fishfooding"
    p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    out, err = p.communicate(json.dumps(req) + "\n")
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
    
    args = parser.parse_args()
    
    out_dir = args.out_dir
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
        "output_directory": f"{out_dir}/audio",
        "output_filename_prefix": f"scene{s_id}_voice"
    })
    
    try:
        res = json.loads(out)
        text = res['result']['content'][0]['text']
        match = re.search(r"Audio saved to: (.*\.wav)", text)
        voice_file = match.group(1)
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
        "local_path": f"{out_dir}/audio",
        "file_name": f"scene{s_id}_music.wav"
    })
    print("Music generation complete.")

    # 3. Image locally then upload (Nano Banana direct to GCS is sometimes flaky)
    print(f"Generating Image locally for scene {s_id}...")
    out, err = run_mcp(["mcp-nanobanana-go", "-t", "stdio"], "nanobanana_image_generation", {
        "prompt": args.image,
        "output_directory": f"{out_dir}/images",
        "aspect_ratio": "16:9"
    })
    try:
        res = json.loads(out)
        text = res['result']['content'][0]['text']
        match = re.search(r"Generated and saved 1 image\(s\): (.*\.png)", text)
        image_file = match.group(1)
        print("Image file:", image_file)
    except Exception as e:
        print("Error parsing image:", e, out, err)
        return

    # Upload to GCS
    print("Uploading image to GCS...")
    gcs_uri = f"gs://{bucket}/story_generator/scene{s_id}_image_{os.path.basename(image_file)}"
    subprocess.run(f"gcloud storage cp {image_file} {gcs_uri}", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Standardize image name for report compatibility
    subprocess.run(f'cp "{image_file}" "{out_dir}/images/scene{s_id}.png"', shell=True, check=True)
    
    # Estimate optimal video duration based on generated voice duration
    video_gen_duration = 6
    try:
        voice_duration = get_duration(voice_file)
        if voice_duration <= 4.2:
            video_gen_duration = 4
        elif voice_duration <= 6.2:
            video_gen_duration = 6
        else:
            video_gen_duration = 8
        print(f"Dynamically selecting Veo video generation duration: {video_gen_duration}s (based on voiceover length {voice_duration:.2f}s)")
    except Exception as e:
        print(f"Could not check voice duration before video generation, using default 6s: {e}")

    # 4. Video (i2v)
    print(f"Generating Video for scene {s_id}...")
    out, err = run_mcp(["mcp-veo-go", "-t", "stdio"], "veo_i2v", {
        "image_uri": gcs_uri,
        "prompt": args.video,
        "model": "veo-3.1-lite-generate-001",
        "bucket": bucket,
        "output_directory": f"{out_dir}/videos",
        "duration": video_gen_duration,
        "aspect_ratio": "16:9",
        "generate_audio": True  # Enable native ambient audio generation
    })
    try:
        res = json.loads(out)
        text = res['result']['content'][0]['text']
        match = re.search(r"Successfully downloaded locally to '.*': (.*\.mp4)", text)
        video_file = match.group(1)
        print("Video file:", video_file)
    except Exception as e:
        print("Error parsing Video:", e, out, err)
        return

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
