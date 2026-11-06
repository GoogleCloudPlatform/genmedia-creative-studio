import argparse
import os
import re
import glob
import json
import subprocess

def get_duration(file_path):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def get_audio_params(file_path):
    cmd = f"ffprobe -v error -select_streams a -show_entries stream=codec_name,sample_rate -of json {file_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        if "streams" in data and len(data["streams"]) > 0:
            stream = data["streams"][0]
            return stream.get("codec_name", "unknown"), int(stream.get("sample_rate", 0))
    except Exception:
        pass
    return "none", 0

def get_video_params(file_path):
    cmd = f"ffprobe -v error -select_streams v -show_entries stream=codec_name,width,height -of json {file_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        if "streams" in data and len(data["streams"]) > 0:
            stream = data["streams"][0]
            return stream.get("codec_name", "unknown"), int(stream.get("width", 0)), int(stream.get("height", 0))
    except Exception:
        pass
    return "unknown", 0, 0

def main():
    parser = argparse.ArgumentParser(description="Evaluate video assembly and scene composition properties (Editor's Quality Room).")
    parser.add_argument("--project_dir", type=str, required=True, help="Path to storybook project directory")
    parser.add_argument("--master_file", type=str, default="final_story.mp4", help="Name of the final master video")
    
    args = parser.parse_args()
    project_dir = args.project_dir
    mixed_dir = f"{project_dir}/mixed"
    audio_dir = f"{project_dir}/audio"
    videos_dir = f"{project_dir}/videos"
    
    print("\n=============================================")
    print("      🎬 EDITOR'S QUALITY CONTROL ROOM       ")
    print("=============================================\n")
    
    # Check project paths
    if not os.path.exists(mixed_dir):
        print(f"Error: Mixed directory {mixed_dir} does not exist. Complete mixing before quality audit.")
        return

    # Find mixed scene clips
    mixed_clips = glob.glob(os.path.join(mixed_dir, "scene*_final.mp4"))
    def sort_key(p):
        m = re.search(r"scene(\d+)", os.path.basename(p))
        return int(m.group(1)) if m else 999
    mixed_clips.sort(key=sort_key)
    
    if not mixed_clips:
        print("No mixed scenes found to audit.")
        return

    report = {
        "project_dir": project_dir,
        "scenes_audited": [],
        "overall_status": "PASS",
        "warnings": [],
        "master_audit": {}
    }
    
    total_expected_duration = 0.0
    critical_errors = 0
    warning_count = 0
    
    # 1. Audit individual scenes
    for i, clip in enumerate(mixed_clips):
        scene_name = os.path.basename(clip)
        scene_id = sort_key(clip)
        print(f"Auditing Scene {scene_id}: {scene_name}...")
        
        # Duration audits
        clip_duration = get_duration(clip)
        total_expected_duration += clip_duration
        
        # Audio track parameters
        a_codec, a_rate = get_audio_params(clip)
        # Video track parameters
        v_codec, w, h = get_video_params(clip)
        
        # Find raw narration voice file to estimate speed-fit factor
        pattern = os.path.join(audio_dir, f"scene{scene_id}_voice*.wav")
        voice_files = glob.glob(pattern)
        voice_duration = 0.0
        tempo_factor = 1.0
        
        # Raw generated clip (standardized by generate_scene.py). Its real length
        # depends on the video model (Veo 4/6/8s, Omni 3-15s).
        raw_video = os.path.join(videos_dir, f"scene{scene_id}_video.mp4")
        raw_duration = get_duration(raw_video) if os.path.exists(raw_video) else 0.0
        if raw_duration <= 0:
            raw_duration = 6.0  # Legacy projects: assume a 6s clip
        
        if voice_files:
            voice_duration = get_duration(voice_files[0])
            # Estimate the speed-fit needed if the voice is longer than the clip
            # (same 0.5s tail as generate_scene.py).
            if voice_duration > raw_duration:
                target = raw_duration - 0.5
                if target < 1.0:
                    target = raw_duration
                tempo_factor = voice_duration / target
                if tempo_factor > 2.0:
                    tempo_factor = 2.0
        
        status = "PASS"
        issues = []
        
        # Core checks
        if a_codec == "none":
            status = "ERROR"
            issues.append("CRITICAL: Missing audio stream in mixed scene.")
            critical_errors += 1
        elif a_codec != "aac" or a_rate != 44100:
            status = "WARNING"
            issues.append(f"Non-standard audio: codec={a_codec}, rate={a_rate}Hz (Expected aac, 44100Hz).")
            warning_count += 1
            
        if v_codec != "h264":
            status = "WARNING"
            issues.append(f"Non-standard video codec: {v_codec} (Expected h264).")
            warning_count += 1

        # Narrator speaking rate evaluation (Tempo Warning)
        if tempo_factor > 1.5:
            status = "WARNING" if status == "PASS" else status
            issues.append(
                f"Tempo Warning: Narration speed-fit tempo is extremely high ({tempo_factor:.2f}x). "
                f"Spoken script is too wordy ({voice_duration:.1f}s) for a {raw_duration:.0f}s clip. Narrator will sound rushed."
            )
            warning_count += 1
            report["warnings"].append({
                "scene": scene_id,
                "type": "TEMPO",
                "message": f"Scene {scene_id} narration speed-fit is too high ({tempo_factor:.2f}x). Consider shortening narration script."
            })
            
        scene_report = {
            "scene_id": scene_id,
            "filename": scene_name,
            "status": status,
            "video_codec": v_codec,
            "resolution": f"{w}x{h}",
            "audio_codec": a_codec,
            "sample_rate": a_rate,
            "duration": clip_duration,
            "voice_original_duration": voice_duration,
            "estimated_tempo": round(tempo_factor, 2),
            "issues": issues
        }
        
        report["scenes_audited"].append(scene_report)
        print(f" - Status: {status}")
        for iss in issues:
            print(f"   * {iss}")
        print("")

    # 2. Audit finalized master movie
    master_path = os.path.join(project_dir, args.master_file)
    print("---------------------------------------------")
    print(f"Auditing Master Compiled Video: {args.master_file}...")
    
    if os.path.exists(master_path):
        m_duration = get_duration(master_path)
        m_a_codec, m_a_rate = get_audio_params(master_path)
        m_v_codec, mw, mh = get_video_params(master_path)
        
        drift = abs(m_duration - total_expected_duration)
        drift_status = "PASS"
        if drift > 0.5:
            drift_status = "WARNING"
            warning_count += 1
            report["warnings"].append({
                "scene": "MASTER",
                "type": "DRIFT",
                "message": f"Master video duration ({m_duration:.2f}s) drifts from sum of scenes ({total_expected_duration:.2f}s) by {drift:.2f}s."
            })
            
        report["master_audit"] = {
            "status": drift_status,
            "duration": m_duration,
            "expected_duration": total_expected_duration,
            "drift_seconds": round(drift, 3),
            "video_codec": m_v_codec,
            "resolution": f"{mw}x{mh}",
            "audio_codec": m_a_codec,
            "sample_rate": m_a_rate
        }
        
        print(f" - Duration: {m_duration:.2f}s (Expected: {total_expected_duration:.2f}s, Drift: {drift:.2f}s)")
        print(f" - Video: {m_v_codec} ({mw}x{mh}) | Audio: {m_a_codec} ({m_a_rate}Hz)")
        print(f" - Master Drift Check: {drift_status}")
    else:
        print(f"WARNING: Master video file {args.master_file} not found. Run assembly first.")
        report["master_audit"] = {"status": "NOT_FOUND"}
        warning_count += 1

    # Overall Status Summary
    if critical_errors > 0:
        report["overall_status"] = "FAIL"
    elif warning_count > 0:
        report["overall_status"] = "WARNING"
    else:
        report["overall_status"] = "PASS"
        
    print(f"\nAudit completed. Overall QC Score: {report['overall_status']} ({critical_errors} errors, {warning_count} warnings)")
    
    # 3. Write diagnostic files
    json_out = os.path.join(project_dir, "quality_report.json")
    with open(json_out, "w") as f:
        json.dump(report, f, indent=2)
        
    md_out = os.path.join(project_dir, "quality_report.md")
    with open(md_out, "w") as f:
        f.write("# 🎬 Editor's Quality Control Room Audit\n\n")
        f.write(f"**Overall Project QC Status**: `{report['overall_status']}`  \n")
        f.write(f"**Critical Errors**: `{critical_errors}` | **Warnings**: `{warning_count}`\n\n")
        
        f.write("## 📹 Scene-Level Evaluation\n\n")
        f.write("| Scene ID | Filename | Status | Duration | Estimated Tempo | Resolution | Video/Audio Codecs | Issues |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- |\n")
        for sc in report["scenes_audited"]:
            iss_str = ", ".join(sc["issues"]) if sc["issues"] else "None"
            f.write(
                f"| {sc['scene_id']} | {sc['filename']} | `{sc['status']}` | {sc['duration']:.2f}s | "
                f"{sc['estimated_tempo']}x | {sc['resolution']} | {sc['video_codec']}/{sc['audio_codec']} | {iss_str} |\n"
            )
            
        f.write("\n## 🎼 Master Assembly Evaluation\n\n")
        if report["master_audit"].get("status") == "NOT_FOUND":
            f.write("*Master assembled video file was not found.*  \n")
        else:
            ma = report["master_audit"]
            f.write(f"*   **Status**: `{ma['status']}`\n")
            f.write(f"*   **Master Duration**: `{ma['duration']:.2f}s` (Expected: `{ma['expected_duration']:.2f}s`)\n")
            f.write(f"*   **A/V Concatenation Drift**: `{ma['drift_seconds']:.3f}s`\n")
            f.write(f"*   **Format Encoding**: `{ma['video_codec']} ({ma['resolution']})` video, `{ma['audio_codec']} ({ma['sample_rate']}Hz)` audio\n")
            
        if report["warnings"]:
            f.write("\n## ⚠️ Editor's Actionable Editorial Notes\n\n")
            for wa in report["warnings"]:
                f.write(f"*   **[Scene {wa['scene']}]** *{wa['type']}*: {wa['message']}\n")
                if wa['type'] == "TEMPO":
                    f.write("    *   *Editorial Recommendation*: Consider shortening the scene narration text in the scripts. Keeping spoken scripts under 12-14 words for 6-second clips ensures natural narration rhythms.\n")

    print(f"Quality reports successfully saved to:\n - {json_out}\n - {md_out}")

if __name__ == "__main__":
    main()
