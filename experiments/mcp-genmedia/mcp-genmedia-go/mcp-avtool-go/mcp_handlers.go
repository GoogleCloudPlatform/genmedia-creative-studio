// Package main implements an MCP server for audio and video processing.

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"github.com/teris-io/shortid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
)

// resolveAVToolOutputFilename applies the shared accept-and-alias precedence
// (design #842 §4a): the canonical output_filename wins over the deprecated
// output_file_name alias. avtool is EXEMPT from extension-forcing (design §4d) —
// the client-provided extension selects the ffmpeg output container/format, so it
// is preserved. The name is still sanitized to a single safe path component
// (traversal defense), which keeps any extension intact. An empty result falls
// through to HandleOutputPreparation's unique-name default.
func resolveAVToolOutputFilename(argsMap map[string]interface{}) string {
	base := common.ResolveOutputFilename(argsMap, "output_file_name")
	if base == "" {
		return ""
	}
	return common.SanitizeBaseFilename(base)
}

// getArguments safely extracts the tool call arguments from an MCP request.
// It checks if the arguments are present and are of the expected type (map[string]interface{}).
// This function helps in gracefully handling malformed or missing arguments.
func getArguments(request mcp.CallToolRequest) (map[string]interface{}, error) {
	if request.Params.Arguments == nil {
		log.Println("Warning: request.Params.Arguments is nil, treating as empty arguments.")
		return make(map[string]interface{}), nil
	}
	argsMap, ok := request.Params.Arguments.(map[string]interface{})
	if !ok {
		log.Printf("Error: request.Params.Arguments is of type %T, not map[string]interface{}", request.Params.Arguments)
		return nil, fmt.Errorf("internal error: request arguments are not in the expected map format (type: %T)", request.Params.Arguments)
	}
	return argsMap, nil
}

// addGetMediaInfoTool defines and registers the 'ffmpeg_get_media_info' tool with the MCP server.
// This tool is designed to extract media information using ffprobe.
func addGetMediaInfoTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_get_media_info",
		mcp.WithDescription("Gets media information (streams, format, etc.) from a media file using ffprobe. Returns JSON output."),
		mcp.WithString("input_media_uri", mcp.Required(), mcp.Description("URI of the input media file (local path or gs://).")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegGetMediaInfoHandler(ctx, request, cfg)
	})
}

// ffmpegGetMediaInfoHandler is the handler function for the 'ffmpeg_get_media_info' tool.
// It processes the request, prepares the input file, executes ffprobe, and returns the media information as a JSON string.
func ffmpegGetMediaInfoHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_get_media_info")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_get_media_info", argsMap)

	inputMediaURI, _ := argsMap["input_media_uri"].(string)
	if strings.TrimSpace(inputMediaURI) == "" {
		return mcp.NewToolResultError("Parameter 'input_media_uri' is required."), nil
	}

	span.SetAttributes(attribute.String("input_media_uri", inputMediaURI))

	localInputMedia, inputCleanup, err := common.PrepareInputFile(ctx, inputMediaURI, "media_info_input", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input media for ffprobe: %v", err)), nil
	}
	defer inputCleanup()

	outputJSON, ffprobeErr := executeGetMediaInfo(ctx, localInputMedia)
	if ffprobeErr != nil {
		span.RecordError(ffprobeErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFprobe execution failed: %v. Output: %s", ffprobeErr, outputJSON)), nil
	}

	var jsTest map[string]interface{}
	if errUnmarshal := json.Unmarshal([]byte(outputJSON), &jsTest); errUnmarshal != nil {
		log.Printf("Warning: FFprobe output for %s was not valid JSON, though command reported success. Output: %s", inputMediaURI, outputJSON)
		return mcp.NewToolResultText(fmt.Sprintf("FFprobe returned non-JSON output: %s", outputJSON)), nil
	}

	duration := time.Since(startTime)
	log.Printf("FFprobe for %s completed in %v.", inputMediaURI, duration)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))
	return mcp.NewToolResultText(outputJSON), nil
}

// addConvertAudioTool defines and registers the 'ffmpeg_convert_audio_wav_to_mp3' tool.
// This tool converts WAV audio files to MP3 format.
func addConvertAudioTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_convert_audio_wav_to_mp3",
		mcp.WithDescription("Converts a WAV audio file to MP3 format using FFMpeg."),
		mcp.WithString("input_audio_uri", mcp.Required(), mcp.Description("URI of the input WAV audio file (local path or gs://).")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'converted.mp3'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output MP3 file (e.g., 'converted.mp3'). If omitted, a unique name is generated.")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output MP3 file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output MP3 file to.")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegConvertAudioHandler(ctx, request, cfg)
	})
}

// ffmpegConvertAudioHandler handles the logic for the 'ffmpeg_convert_audio_wav_to_mp3' tool.
// It manages file preparation, executes the FFmpeg conversion command, and handles the output.
func ffmpegConvertAudioHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_convert_audio_wav_to_mp3")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_convert_audio_wav_to_mp3", argsMap)

	inputAudioURI, _ := argsMap["input_audio_uri"].(string)
	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_convert_audio_wav_to_mp3: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}
	if inputAudioURI == "" {
		return mcp.NewToolResultError("Parameter 'input_audio_uri' is required."), nil
	}

	span.SetAttributes(
		attribute.String("input_audio_uri", inputAudioURI),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputAudio, inputCleanup, err := common.PrepareInputFile(ctx, inputAudioURI, "input_audio", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input audio: %v", err)), nil
	}
	defer inputCleanup()

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, "mp3")
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	_, ffmpegErr := runFFmpegCommand(ctx, "-y", "-i", localInputAudio, "-acodec", "libmp3lame", tempOutputFile)
	if ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg conversion failed: %v", ffmpegErr)), nil
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Audio conversion to MP3 completed in %v.", duration))
	if finalLocalPath != "" {
		if outputLocalDir != "" {
			messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
		} else {
			messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not uploaded).", finalLocalPath))
		}
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addCreateGifTool defines and registers the 'ffmpeg_video_to_gif' tool.
// This tool converts a video file into a GIF animation.
func addCreateGifTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_video_to_gif",
		mcp.WithDescription("Creates a GIF from an input video using a two-pass FFMpeg process (palette generation and palette use)."),
		mcp.WithString("input_video_uri", mcp.Required(), mcp.Description("URI of the input video file (local path or gs://).")),
		mcp.WithNumber("scale_width_factor", mcp.DefaultNumber(0.33), mcp.Description("Factor to scale the input video's width by (e.g., 0.33 for 33%). Height is scaled automatically to maintain aspect ratio. Use 1.0 for original width.")),
		mcp.WithNumber("fps", mcp.DefaultNumber(15), mcp.Min(1), mcp.Max(50), mcp.Description("Frames per second for the output GIF (e.g., 10, 15, 25).")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'animation.gif'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output GIF file (e.g., 'animation.gif'). If omitted, a unique name is generated.")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output GIF file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output GIF file to (uses GENMEDIA_BUCKET if set and this is empty).")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegVideoToGifHandler(ctx, request, cfg)
	})
}

// ffmpegVideoToGifHandler orchestrates the two-pass process of creating a GIF from a video.
// It first generates a color palette from the source video and then uses this palette to create a high-quality GIF.
func ffmpegVideoToGifHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_video_to_gif")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_video_to_gif", argsMap)

	inputVideoURI, _ := argsMap["input_video_uri"].(string)
	if strings.TrimSpace(inputVideoURI) == "" {
		return mcp.NewToolResultError("Parameter 'input_video_uri' is required."), nil
	}

	scaleFactorParam, _ := argsMap["scale_width_factor"].(float64)
	if scaleFactorParam <= 0 {
		scaleFactorParam = 0.33
	}
	fpsParam, _ := argsMap["fps"].(float64)
	if fpsParam <= 0 {
		fpsParam = 15
	}
	if fpsParam < 1 {
		fpsParam = 1
	}
	if fpsParam > 50 {
		fpsParam = 50
	}

	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)
	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_video_to_gif: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}

	span.SetAttributes(
		attribute.String("input_video_uri", inputVideoURI),
		attribute.Float64("scale_width_factor", scaleFactorParam),
		attribute.Float64("fps", fpsParam),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputVideo, inputCleanup, err := common.PrepareInputFile(ctx, inputVideoURI, "input_video_for_gif", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input video: %v", err)), nil
	}
	defer inputCleanup()

	gifProcessingTempDir, err := os.MkdirTemp("", "gif_processing_")
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to create temp directory for GIF processing: %v", err)), nil
	}
	defer func() {
		log.Printf("Cleaning up GIF processing temporary directory: %s", gifProcessingTempDir)
		_ = os.RemoveAll(gifProcessingTempDir)
	}()

	palettePath := filepath.Join(gifProcessingTempDir, "palette.png")
	paletteVFFilter := fmt.Sprintf("fps=%.2f,scale=iw*%.2f:-1:flags=lanczos+accurate_rnd+full_chroma_inp,palettegen", fpsParam, scaleFactorParam)
	log.Printf("Generating palette with VF filter: %s", paletteVFFilter)
	_, ffmpegErrPalette := runFFmpegCommand(ctx, "-y", "-i", localInputVideo, "-vf", paletteVFFilter, palettePath)
	if ffmpegErrPalette != nil {
		span.RecordError(ffmpegErrPalette)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg palette generation failed: %v", ffmpegErrPalette)), nil
	}
	log.Printf("Palette generated successfully: %s", palettePath)

	var finalGifFilename string
	if strings.TrimSpace(outputFileName) == "" {
		uid, _ := shortid.Generate()
		finalGifFilename = fmt.Sprintf("ffmpeg_gif_%s.gif", uid)
	} else {
		finalGifFilename = outputFileName
		if !strings.HasSuffix(strings.ToLower(finalGifFilename), ".gif") {
			finalGifFilename += ".gif"
		}
	}
	tempGifOutputPath := filepath.Join(gifProcessingTempDir, finalGifFilename)

	gifLavfiFilter := fmt.Sprintf("fps=%.2f,scale=iw*%.2f:-1:flags=lanczos+accurate_rnd+full_chroma_inp [x]; [x][1:v] paletteuse", fpsParam, scaleFactorParam)
	log.Printf("Creating GIF with LAVFI filter: %s", gifLavfiFilter)
	_, ffmpegErrGif := runFFmpegCommand(ctx, "-y", "-i", localInputVideo, "-i", palettePath, "-lavfi", gifLavfiFilter, tempGifOutputPath)
	if ffmpegErrGif != nil {
		span.RecordError(ffmpegErrGif)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg GIF creation failed: %v", ffmpegErrGif)), nil
	}
	log.Printf("GIF created successfully in temp location: %s", tempGifOutputPath)

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempGifOutputPath, finalGifFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process generated GIF: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("GIF creation completed in %v.", duration.Round(time.Second)))
	if finalLocalPath != "" {
		if outputLocalDir != "" {
			messageParts = append(messageParts, fmt.Sprintf("Output GIF saved locally to: %s.", finalLocalPath))
		} else if outputGCSBucket == "" || finalGCSPath == "" {
			messageParts = append(messageParts, fmt.Sprintf("Temporary GIF output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
		}
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output GIF uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location (local/GCS) was processed or an issue occurred in processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addCombineAudioVideoTool defines and registers the 'ffmpeg_combine_audio_and_video' tool.
// This tool merges a video stream from one file and an audio stream from another into a single video file.
func addCombineAudioVideoTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_combine_audio_and_video",
		mcp.WithDescription("Combines separate audio and video files into a single video file."),
		mcp.WithString("input_video_uri", mcp.Required(), mcp.Description("URI of the input video file (local path or gs://).")),
		mcp.WithString("input_audio_uri", mcp.Required(), mcp.Description("URI of the input audio file (local path or gs://).")),
		mcp.WithNumber("input_video_volume_db_change", mcp.Description("Optional. Volume change in dB for the input video's audio track (e.g., -10).")),
		mcp.WithNumber("input_audio_volume_db_change", mcp.Description("Optional. Volume change in dB for the input audio track (e.g., +5).")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'combined.mp4'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output video file (e.g., 'combined.mp4').")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output video file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output video file to.")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegCombineAudioVideoHandler(ctx, request, cfg)
	})
}

// ffmpegCombineAudioVideoHandler is the handler for the audio/video combination tool.
// It prepares the separate video and audio input files, then uses FFmpeg to combine them,
// copying the video codec and taking the audio from the second input.
func ffmpegCombineAudioVideoHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_combine_audio_and_video")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_combine_audio_and_video", argsMap)

	inputVideoURI, _ := argsMap["input_video_uri"].(string)
	inputAudioURI, _ := argsMap["input_audio_uri"].(string)
	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	inputVideoVolume, hasVideoVol := argsMap["input_video_volume_db_change"].(float64)
	inputAudioVolume, hasAudioVol := argsMap["input_audio_volume_db_change"].(float64)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_combine_audio_and_video: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}
	if inputVideoURI == "" || inputAudioURI == "" {
		return mcp.NewToolResultError("Parameters 'input_video_uri' and 'input_audio_uri' are required."), nil
	}

	span.SetAttributes(
		attribute.String("input_video_uri", inputVideoURI),
		attribute.String("input_audio_uri", inputAudioURI),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputVideo, videoCleanup, err := common.PrepareInputFile(ctx, inputVideoURI, "input_video", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input video: %v", err)), nil
	}
	defer videoCleanup()

	localInputAudio, audioCleanup, err := common.PrepareInputFile(ctx, inputAudioURI, "input_audio", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input audio: %v", err)), nil
	}
	defer audioCleanup()

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, "mp4")
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	// Check if video has audio
	mediaInfoJSON, err := executeGetMediaInfo(ctx, localInputVideo)
	hasAudio := false
	if err == nil {
		var info struct {
			Streams []struct {
				CodecType string `json:"codec_type"`
			} `json:"streams"`
		}
		if json.Unmarshal([]byte(mediaInfoJSON), &info) == nil {
			for _, s := range info.Streams {
				if s.CodecType == "audio" {
					hasAudio = true
					break
				}
			}
		}
	}

	var ffmpegErr error
	if hasAudio {
		// Mix audio tracks using amix filter
		var filterParts []string

		if hasVideoVol {
			filterParts = append(filterParts, fmt.Sprintf("[0:a]volume=%.2fdB[v_a]", inputVideoVolume))
		} else {
			filterParts = append(filterParts, "[0:a]anull[v_a]")
		}

		if hasAudioVol {
			filterParts = append(filterParts, fmt.Sprintf("[1:a]volume=%.2fdB[a_a]", inputAudioVolume))
		} else {
			filterParts = append(filterParts, "[1:a]anull[a_a]")
		}

		filterParts = append(filterParts, "[v_a][a_a]amix=inputs=2:duration=longest[a]")
		filterComplex := strings.Join(filterParts, "; ")

		_, ffmpegErr = runFFmpegCommand(ctx, "-y", "-i", localInputVideo, "-i", localInputAudio, "-filter_complex", filterComplex, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", tempOutputFile)
	} else {
		// Just add the audio track directly if video has no audio
		if hasAudioVol {
			filterComplex := fmt.Sprintf("[1:a]volume=%.2fdB[a]", inputAudioVolume)
			_, ffmpegErr = runFFmpegCommand(ctx, "-y", "-i", localInputVideo, "-i", localInputAudio, "-filter_complex", filterComplex, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", tempOutputFile)
		} else {
			_, ffmpegErr = runFFmpegCommand(ctx, "-y", "-i", localInputVideo, "-i", localInputAudio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", tempOutputFile)
		}
	}

	if ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg combine audio/video failed: %v", ffmpegErr)), nil
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Audio and video combination completed in %v.", duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addOverlayImageOnVideoTool defines and registers the 'ffmpeg_overlay_image_on_video' tool.
// This tool places an image on top of a video at specified coordinates.
func addOverlayImageOnVideoTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_overlay_image_on_video",
		mcp.WithDescription("Overlays an image onto a video at specified coordinates."),
		mcp.WithString("input_video_uri", mcp.Required(), mcp.Description("URI of the input video file (local path or gs://).")),
		mcp.WithString("input_image_uri", mcp.Required(), mcp.Description("URI of the input image file (local path or gs://).")),
		mcp.WithNumber("x_coordinate", mcp.DefaultNumber(0), mcp.Description("X coordinate for the overlay (top-left).")),
		mcp.WithNumber("y_coordinate", mcp.DefaultNumber(0), mcp.Description("Y coordinate for the overlay (top-left).")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'overlayed_video.mp4'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output video file (e.g., 'overlayed_video.mp4').")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output video file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output video file to.")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegOverlayImageHandler(ctx, request, cfg)
	})
}

// ffmpegOverlayImageHandler handles the request to overlay an image onto a video.
// It prepares both the video and image files, then uses FFmpeg's overlay filter to perform the composition.
func ffmpegOverlayImageHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_overlay_image_on_video")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_overlay_image_on_video", argsMap)

	inputVideoURI, _ := argsMap["input_video_uri"].(string)
	inputImageURI, _ := argsMap["input_image_uri"].(string)
	xCoordFloat, _ := argsMap["x_coordinate"].(float64)
	yCoordFloat, _ := argsMap["y_coordinate"].(float64)
	xCoord := int(xCoordFloat)
	yCoord := int(yCoordFloat)
	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_overlay_image_on_video: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}
	if inputVideoURI == "" || inputImageURI == "" {
		return mcp.NewToolResultError("Parameters 'input_video_uri' and 'input_image_uri' are required."), nil
	}

	span.SetAttributes(
		attribute.String("input_video_uri", inputVideoURI),
		attribute.String("input_image_uri", inputImageURI),
		attribute.Int("x_coordinate", xCoord),
		attribute.Int("y_coordinate", yCoord),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputVideo, videoCleanup, err := common.PrepareInputFile(ctx, inputVideoURI, "input_video", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input video: %v", err)), nil
	}
	defer videoCleanup()

	localInputImage, imageCleanup, err := common.PrepareInputFile(ctx, inputImageURI, "input_image", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input image: %v", err)), nil
	}
	defer imageCleanup()

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, "mp4")
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	overlayFilter := fmt.Sprintf("[0:v][1:v]overlay=%d:%d", xCoord, yCoord)
	_, ffmpegErr := runFFmpegCommand(ctx, "-y", "-i", localInputVideo, "-i", localInputImage, "-filter_complex", overlayFilter, tempOutputFile)
	if ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg overlay image failed: %v", ffmpegErr)), nil
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Image overlay on video completed in %v.", duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addConcatenateMediaTool defines and registers the 'ffmpeg_concatenate_media_files' tool.
// This tool is capable of joining multiple media files into a single file.
// It has special handling for WAV files to ensure compatibility.
func addConcatenateMediaTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_concatenate_media_files",
		mcp.WithDescription("Concatenates multiple media files. If output is WAV, inputs must be PCM WAV; otherwise, inputs are standardized to MP4/AAC before concatenation."),
		mcp.WithArray("input_media_uris", mcp.Required(), mcp.Description("Array of URIs for the input media files (local paths or gs://)."), mcp.Items(map[string]any{"type": "string"})),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'concatenated.mp4'). The client-provided extension is honored and selects the output format (and determines behavior for audio concatenation). Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output file (e.g., 'concatenated.mp4'). Extension determines behavior for audio concatenation.")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output file to.")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegConcatenateMediaHandler(ctx, request, cfg)
	})
}

// ffmpegConcatenateMediaHandler provides the logic for concatenating media files.
// It handles two primary cases: direct concatenation of compatible PCM WAV files, and
// a more general case where inputs are first standardized to a common format (MP4/AAC)
// before being concatenated. This ensures a reliable join for a variety of input formats.
func ffmpegConcatenateMediaHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_concatenate_media_files")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_concatenate_media_files", argsMap)

	inputMediaURIsRaw, _ := argsMap["input_media_uris"].([]interface{})
	var inputMediaURIs []string
	for _, item := range inputMediaURIsRaw {
		if strItem, ok := item.(string); ok {
			inputMediaURIs = append(inputMediaURIs, strItem)
		}
	}

	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_concatenate_media_files: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}
	if len(inputMediaURIs) < 1 {
		if len(inputMediaURIs) == 0 {
			return mcp.NewToolResultError("At least one media file is required for concatenation."), nil
		}
		log.Println("Warning: Only one input file provided for concatenation. Will process it as a single file operation.")
	}
	if len(inputMediaURIs) < 2 && len(inputMediaURIs) > 0 {
		log.Println("Warning: Only one input file provided for concatenation. The 'concatenation' will essentially be a copy or re-encode of this single file through the chosen path (PCM or AAC standardization).")
	}

	span.SetAttributes(
		attribute.StringSlice("input_media_uris", inputMediaURIs),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	var localInputFilePaths []string
	var inputCleanups []func()
	defer func() {
		for _, c := range inputCleanups {
			c()
		}
	}()

	for i, uri := range inputMediaURIs {
		localPath, cleanup, errPrep := common.PrepareInputFile(ctx, uri, fmt.Sprintf("concat_input_%d", i), cfg.ProjectID)
		if errPrep != nil {
			span.RecordError(errPrep)
			return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input media file %s: %v", uri, errPrep)), nil
		}
		inputCleanups = append(inputCleanups, cleanup)
		localInputFilePaths = append(localInputFilePaths, localPath)
	}

	defaultOutputExt := "mp4"
	if len(localInputFilePaths) > 0 {
		firstExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(localInputFilePaths[0]), "."))
		if firstExt == "wav" || firstExt == "mp3" || firstExt == "aac" || firstExt == "m4a" {
			defaultOutputExt = firstExt
		}
	}
	if outputFileName != "" {
		userExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(outputFileName), "."))
		if userExt != "" {
			defaultOutputExt = userExt
		}
	}

	tempOutputFile, finalOutputFilename, outputProcessingCleanup, err := common.HandleOutputPreparation(outputFileName, defaultOutputExt)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputProcessingCleanup()

	isOutputWav := strings.ToLower(defaultOutputExt) == "wav"

	if isOutputWav {
		log.Println("Output is WAV. Checking if all inputs are compatible PCM WAV for direct concatenation.")
		allInputsAreCompatiblePcmWav := true
		var firstPcmInfo struct {
			SampleFmt   string
			SampleRate  string
			Channels    int
			CodecName   string
			Initialized bool
		}
		var actualPcmInputPaths []string

		if len(localInputFilePaths) == 0 {
			allInputsAreCompatiblePcmWav = false
		}

		for i, path := range localInputFilePaths {
			log.Printf("Checking codec and properties for input %d: %s", i+1, path)
			mediaInfoJSON, ffprobeErr := executeGetMediaInfo(ctx, path)
			if ffprobeErr != nil {
				allInputsAreCompatiblePcmWav = false
				log.Printf("Failed to get media info for input %s: %v. Cannot ensure PCM WAV compatibility.", path, ffprobeErr)
				break
			}

			var info struct {
				Streams []struct {
					CodecType  string `json:"codec_type"`
					CodecName  string `json:"codec_name"`
					SampleFmt  string `json:"sample_fmt"`
					SampleRate string `json:"sample_rate"`
					Channels   int    `json:"channels"`
				} `json:"streams"`
			}
			if err := json.Unmarshal([]byte(mediaInfoJSON), &info); err != nil {
				allInputsAreCompatiblePcmWav = false
				log.Printf("Failed to parse media info for input %s: %v. Cannot ensure PCM WAV compatibility.", path, err)
				break
			}

			isCurrentFilePcm := false
			var currentStreamInfo struct {
				SampleFmt  string
				SampleRate string
				Channels   int
				CodecName  string
			}
			audioStreamFound := false

			for _, stream := range info.Streams {
				if stream.CodecType == "audio" {
					audioStreamFound = true
					log.Printf("Audio stream found for %s: codec_name='%s', sample_fmt='%s', sample_rate='%s', channels=%d",
						path, stream.CodecName, stream.SampleFmt, stream.SampleRate, stream.Channels)
					if strings.HasPrefix(stream.CodecName, "pcm_") {
						isCurrentFilePcm = true
						currentStreamInfo.SampleFmt = stream.SampleFmt
						currentStreamInfo.SampleRate = stream.SampleRate
						currentStreamInfo.Channels = stream.Channels
						currentStreamInfo.CodecName = stream.CodecName
					} else {
						isCurrentFilePcm = false
					}
					break
				}
			}

			if !audioStreamFound {
				allInputsAreCompatiblePcmWav = false
				log.Printf("No audio stream found in input %s. Cannot treat as compatible PCM WAV.", path)
				break
			}
			if !isCurrentFilePcm {
				allInputsAreCompatiblePcmWav = false
				log.Printf("Input file %s is not PCM WAV (audio codec: %s).", path, currentStreamInfo.CodecName)
				break
			}

			if !firstPcmInfo.Initialized {
				firstPcmInfo.SampleFmt = currentStreamInfo.SampleFmt
				firstPcmInfo.SampleRate = currentStreamInfo.SampleRate
				firstPcmInfo.Channels = currentStreamInfo.Channels
				firstPcmInfo.CodecName = currentStreamInfo.CodecName
				firstPcmInfo.Initialized = true
				log.Printf("First PCM WAV input %s (%s) sets standard: SR=%s, Fmt=%s, Ch=%d",
					path, firstPcmInfo.CodecName, firstPcmInfo.SampleRate, firstPcmInfo.SampleFmt, firstPcmInfo.Channels)
			} else {
				if currentStreamInfo.SampleRate != firstPcmInfo.SampleRate ||
					currentStreamInfo.Channels != firstPcmInfo.Channels ||
					currentStreamInfo.SampleFmt != firstPcmInfo.SampleFmt {
					allInputsAreCompatiblePcmWav = false
					log.Printf("Input PCM WAV file %s (%s, SR=%s, Fmt=%s, Ch=%d) is incompatible with the first PCM WAV file (%s, SR=%s, Fmt=%s, Ch=%d).",
						path, currentStreamInfo.CodecName, currentStreamInfo.SampleRate, currentStreamInfo.SampleFmt, currentStreamInfo.Channels,
						firstPcmInfo.CodecName, firstPcmInfo.SampleRate, firstPcmInfo.SampleFmt, firstPcmInfo.Channels)
					break
				}
				log.Printf("Input PCM WAV file %s is compatible with the first.", path)
			}
			actualPcmInputPaths = append(actualPcmInputPaths, path)
		}

		if allInputsAreCompatiblePcmWav && firstPcmInfo.Initialized {
			log.Println("All inputs are compatible PCM WAV. Proceeding with direct PCM concatenation.")

			concatListTempDir, errListTempDir := os.MkdirTemp("", "concat_list_pcm_")
			if errListTempDir != nil {
				span.RecordError(errListTempDir)
				return mcp.NewToolResultError(fmt.Sprintf("Failed to create temp dir for PCM concat list: %v", errListTempDir)), nil
			}
			defer func() {
				log.Printf("Cleaning up PCM concat list temporary directory: %s", concatListTempDir)
				_ = os.RemoveAll(concatListTempDir)
			}()

			concatListPath := filepath.Join(concatListTempDir, "concat_list_pcm.txt")
			var fileListContent strings.Builder
			for _, pcmPath := range actualPcmInputPaths {
				absPath, absErr := filepath.Abs(pcmPath)
				if absErr != nil {
					span.RecordError(absErr)
					return mcp.NewToolResultError(fmt.Sprintf("Failed to get absolute path for PCM file %s: %v", pcmPath, absErr)), nil
				}
				fmt.Fprintf(&fileListContent, "file '%s'\n", absPath)
			}
			if errWriteList := os.WriteFile(concatListPath, []byte(fileListContent.String()), 0644); errWriteList != nil {
				span.RecordError(errWriteList)
				return mcp.NewToolResultError(fmt.Sprintf("Failed to write PCM concat list file: %v", errWriteList)), nil
			}

			concatCmdArgs := []string{"-y", "-f", "concat", "-safe", "0", "-i", concatListPath, "-c", "copy", tempOutputFile}
			log.Printf("Attempting direct PCM concatenation of WAV files using concat demuxer (-c copy).")
			_, ffmpegErr := runFFmpegCommand(ctx, concatCmdArgs...)
			if ffmpegErr != nil {
				span.RecordError(ffmpegErr)
				return mcp.NewToolResultError(fmt.Sprintf("FFMpeg direct PCM WAV concatenation failed: %v. Ensure input WAVs have compatible PCM formats (sample rate, channels, bit depth).", ffmpegErr)), nil
			}
			log.Println("Direct PCM WAV concatenation successful.")

		} else {
			log.Println("Output is WAV, but not all inputs are compatible PCM WAV, or an error occurred checking. Rejecting operation.")
			return mcp.NewToolResultError("Error: When outputting to WAV, all input files must be PCM WAV with identical characteristics (sample rate, sample format, and channel count). Please convert inputs to a common PCM WAV format or choose a different output format (e.g., M4A, MP4)."), nil
		}

	} else {
		log.Println("Output is not WAV. Proceeding with standardization to MP4/AAC before concatenation.")
		var standardizedFiles []string
		standardizationTempDir, errStdTempDir := os.MkdirTemp("", "concat_standardize_")
		if errStdTempDir != nil {
			span.RecordError(errStdTempDir)
			return mcp.NewToolResultError(fmt.Sprintf("Failed to create temp dir for standardization: %v", errStdTempDir)), nil
		}
		defer func() {
			log.Printf("Cleaning up standardization temporary directory: %s", standardizationTempDir)
			_ = os.RemoveAll(standardizationTempDir)
		}()

		commonWidth := 1280
		commonHeight := 720
		commonFPS := "24"
		commonSampleRate := "48000"
		commonChannels := "2"

		for i, localInputFile := range localInputFilePaths {
			baseName := filepath.Base(localInputFile)
			ext := filepath.Ext(baseName)
			standardizedOutputName := fmt.Sprintf("standardized_%d_%s.mp4", i, strings.TrimSuffix(baseName, ext))
			standardizedOutputPath := filepath.Join(standardizationTempDir, standardizedOutputName)

			mediaInfoJSON, ffprobeErr := executeGetMediaInfo(ctx, localInputFile)
			isAudioOnly := false
			if ffprobeErr == nil {
				var info struct {
					Streams []struct {
						CodecType string `json:"codec_type"`
					} `json:"streams"`
				}
				if json.Unmarshal([]byte(mediaInfoJSON), &info) == nil {
					hasVideo := false
					for _, s := range info.Streams {
						if s.CodecType == "video" {
							hasVideo = true
							break
						}
					}
					if !hasVideo && len(info.Streams) > 0 {
						isAudioOnly = true
					}
				}
			}

			var standardizeCmdArgs []string
			if isAudioOnly {
				log.Printf("Standardizing audio-only input %d ('%s') to AAC in MP4 container: '%s'", i+1, localInputFile, standardizedOutputPath)
				standardizeCmdArgs = []string{"-y", "-i", localInputFile, "-vn", "-c:a", "aac", "-ar", commonSampleRate, "-ac", commonChannels, "-b:a", "192k", standardizedOutputPath}
			} else {
				log.Printf("Standardizing video/mixed input %d ('%s') to H264/AAC in MP4 container: '%s'", i+1, localInputFile, standardizedOutputPath)
				vfArgs := fmt.Sprintf("scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:0:0,fps=%s", commonWidth, commonHeight, commonWidth, commonHeight, commonFPS)
				standardizeCmdArgs = []string{"-y", "-i", localInputFile, "-vf", vfArgs, "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-ar", commonSampleRate, "-ac", commonChannels, "-b:a", "192k", standardizedOutputPath}
			}

			_, stdErr := runFFmpegCommand(ctx, standardizeCmdArgs...)
			if stdErr != nil {
				span.RecordError(stdErr)
				return mcp.NewToolResultError(fmt.Sprintf("Failed to standardize file %s: %v", localInputFile, stdErr)), nil
			}
			standardizedFiles = append(standardizedFiles, standardizedOutputPath)
		}

		if len(standardizedFiles) == 0 {
			return mcp.NewToolResultError("No files were successfully standardized for concatenation."), nil
		}

		concatListTempDir, errListTempDir := os.MkdirTemp("", "concat_list_std_")
		if errListTempDir != nil {
			span.RecordError(errListTempDir)
			return mcp.NewToolResultError(fmt.Sprintf("Failed to create temp dir for standardized concat list: %v", errListTempDir)), nil
		}
		defer func() {
			log.Printf("Cleaning up standardized concat list temporary directory: %s", concatListTempDir)
			_ = os.RemoveAll(concatListTempDir)
		}()

		concatListPath := filepath.Join(concatListTempDir, "concat_list_std.txt")
		var fileListContent strings.Builder
		for _, sf := range standardizedFiles {
			absPath, absErr := filepath.Abs(sf)
			if absErr != nil {
				span.RecordError(absErr)
				return mcp.NewToolResultError(fmt.Sprintf("Failed to get absolute path for standardized file %s: %v", sf, absErr)), nil
			}
			fmt.Fprintf(&fileListContent, "file '%s'\n", absPath)
		}
		if errWriteList := os.WriteFile(concatListPath, []byte(fileListContent.String()), 0644); errWriteList != nil {
			span.RecordError(errWriteList)
			return mcp.NewToolResultError(fmt.Sprintf("Failed to write standardized concat list file: %v", errWriteList)), nil
		}

		concatDemuxerCmdArgs := []string{"-y", "-f", "concat", "-safe", "0", "-i", concatListPath, "-c", "copy", tempOutputFile}
		log.Printf("Attempting concatenation of standardized files using concat demuxer (-c copy).")
		_, ffmpegErr := runFFmpegCommand(ctx, concatDemuxerCmdArgs...)
		if ffmpegErr != nil {
			span.RecordError(ffmpegErr)
			return mcp.NewToolResultError(fmt.Sprintf("FFMpeg concatenation (concat demuxer with -c copy) failed: %v", ffmpegErr)), nil
		}
		log.Println("Concatenation of standardized files successful.")
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Media concatenation completed in %v.", duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" && (outputGCSBucket == "" || finalGCSPath == "") {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing, or an issue occurred.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addTrimMediaTool defines and registers the 'ffmpeg_trim_media' tool.
// This tool extracts a single contiguous segment (a cut/trim) from an audio or video
// file. It works identically for audio and video because it operates on ffmpeg's
// -ss/-t seek-and-duration options, which apply to any stream type.
func addTrimMediaTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_trim_media",
		mcp.WithDescription("Trims (cuts) a single segment from an audio or video file, keeping only the portion between a start time and an end time (or for a given duration). Works for both audio and video inputs. "+
			"By default the segment is extracted with a fast, lossless stream copy (no re-encode). Because a stream copy can only begin on a keyframe, the actual cut may start at the nearest keyframe at or before the requested start time, so it may not be exactly frame-accurate. "+
			"Set re_encode=true for a frame-accurate cut at the exact start time; this re-encodes the segment, which is slower and slightly lossy. If a stream copy is not possible for the chosen output container, the tool automatically falls back to a re-encode."),
		mcp.WithString("input_media_uri", mcp.Required(), mcp.Description("URI of the input audio or video file (local path or gs://).")),
		mcp.WithNumber("start_time", mcp.Required(), mcp.Description("Start time of the segment to keep, in seconds from the beginning of the file (e.g., 5 or 12.5). Must be within the file's duration.")),
		mcp.WithNumber("duration", mcp.Description("Optional. Length of the segment to keep, in seconds (e.g., 10). Provide either 'duration' or 'end_time'. If both are given, 'duration' takes precedence.")),
		mcp.WithNumber("end_time", mcp.Description("Optional. End time of the segment to keep, in seconds from the beginning of the file. Must be greater than 'start_time'. Used only when 'duration' is not provided.")),
		mcp.WithBoolean("re_encode", mcp.DefaultBool(false), mcp.Description("Optional. When true, re-encodes the segment for a frame-accurate cut at the exact start time instead of the default fast, lossless stream copy. Defaults to false.")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'clip.mp4'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated and the input's extension is preserved. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output file (e.g., 'clip.mp4').")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output file to (uses GENMEDIA_BUCKET if set and this is empty).")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegTrimMediaHandler(ctx, request, cfg)
	})
}

// ffmpegTrimMediaHandler is the handler for the 'ffmpeg_trim_media' tool. It prepares
// the input, resolves the requested time range (start plus either an explicit duration
// or an end time), validates the range against the file's actual duration, and then
// extracts the segment. The output container defaults to the input's extension so a
// stream copy stays valid, unless the caller specifies an output filename with its own
// extension.
func ffmpegTrimMediaHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_trim_media")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_trim_media", argsMap)

	inputMediaURI, _ := argsMap["input_media_uri"].(string)
	if strings.TrimSpace(inputMediaURI) == "" {
		return mcp.NewToolResultError("Parameter 'input_media_uri' is required."), nil
	}

	startSeconds, hasStart := argsMap["start_time"].(float64)
	if !hasStart {
		return mcp.NewToolResultError("Parameter 'start_time' is required and must be a number (seconds)."), nil
	}
	if startSeconds < 0 {
		return mcp.NewToolResultError("Parameter 'start_time' must not be negative."), nil
	}

	durationSeconds, hasDuration := argsMap["duration"].(float64)
	endSeconds, hasEnd := argsMap["end_time"].(float64)

	switch {
	case hasDuration:
		if durationSeconds <= 0 {
			return mcp.NewToolResultError("Parameter 'duration' must be greater than 0."), nil
		}
	case hasEnd:
		if endSeconds <= startSeconds {
			return mcp.NewToolResultError("Parameter 'end_time' must be greater than 'start_time'."), nil
		}
		durationSeconds = endSeconds - startSeconds
	default:
		return mcp.NewToolResultError("Either 'duration' or 'end_time' must be provided."), nil
	}

	reEncode, _ := argsMap["re_encode"].(bool)
	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_trim_media: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}

	span.SetAttributes(
		attribute.String("input_media_uri", inputMediaURI),
		attribute.Float64("start_time", startSeconds),
		attribute.Float64("duration", durationSeconds),
		attribute.Bool("re_encode", reEncode),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputMedia, inputCleanup, err := common.PrepareInputFile(ctx, inputMediaURI, "trim_input", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input media: %v", err)), nil
	}
	defer inputCleanup()

	// Validate the requested range against the file's actual duration when it can be
	// determined. If the duration is unknown (some streams don't report one), skip
	// validation and let ffmpeg handle it rather than rejecting a valid request.
	if mediaDuration, probeErr := probeMediaDurationSeconds(ctx, localInputMedia); probeErr != nil {
		log.Printf("Handler ffmpeg_trim_media: could not determine input duration, skipping range validation: %v", probeErr)
	} else if startSeconds >= mediaDuration {
		return mcp.NewToolResultError(fmt.Sprintf("Parameter 'start_time' (%.3fs) is at or beyond the input's duration (%.3fs).", startSeconds, mediaDuration)), nil
	}

	// Default the output container to the input's extension so a stream copy remains
	// valid. A client-provided output filename extension overrides this.
	defaultOutputExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(localInputMedia), "."))
	if defaultOutputExt == "" {
		defaultOutputExt = "mp4"
	}
	if outputFileName != "" {
		if userExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(outputFileName), ".")); userExt != "" {
			defaultOutputExt = userExt
		}
	}

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, defaultOutputExt)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	usedReEncode, ffmpegErr := executeTrimMedia(ctx, localInputMedia, tempOutputFile, startSeconds, durationSeconds, reEncode)
	if ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg trim failed: %v", ffmpegErr)), nil
	}
	span.SetAttributes(attribute.Bool("used_re_encode", usedReEncode))

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	mode := "stream copy (no re-encode)"
	if usedReEncode {
		mode = "re-encode"
	}
	messageParts = append(messageParts, fmt.Sprintf("Trim of %.3fs starting at %.3fs (%s) completed in %v.", durationSeconds, startSeconds, mode, duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" && (outputGCSBucket == "" || finalGCSPath == "") {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addExtractFrameTool defines and registers the 'ffmpeg_extract_frame' tool.
// This tool extracts a single still image (PNG/JPEG) from a video, either the exact
// last frame (default) or the frame at a given timestamp. The output is a plain image
// path/URI suitable as a reference-image input for downstream conditioning (e.g.
// mcp-omni-go's omni_video_generation, or Veo first/last / reference-image inputs).
func addExtractFrameTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_extract_frame",
		mcp.WithDescription("Extracts a single still frame from a video as a PNG or JPEG image. "+
			"Use mode=last_frame (default) to capture the exact final frame of the clip, or mode=at_timestamp to capture the frame at a specific time offset. "+
			"The output is a single image file (local path and/or GCS URI), directly usable as a reference-image input for downstream conditioning (e.g. chaining video segments by conditioning the next segment on the last frame of the previous one). "+
			"PNG (default) is lossless and best for conditioning; JPEG is available via output_format or the output_filename extension. Fails if the input has no video stream."),
		mcp.WithString("input_media_uri", mcp.Required(), mcp.Description("URI of the input video file (local path or gs://). Must contain a video stream.")),
		mcp.WithString("mode", mcp.DefaultString(extractModeLastFrame), mcp.Enum(extractModeLastFrame, extractModeAtTimestamp), mcp.Description("Optional. 'last_frame' (default) extracts the exact final frame; 'at_timestamp' extracts the frame at 'timestamp' seconds.")),
		mcp.WithNumber("timestamp", mcp.Description("Conditional. Time offset in seconds from the start of the video (e.g., 1.5). Required when mode=at_timestamp; must be >= 0 and less than the input's duration. Ignored when mode=last_frame.")),
		mcp.WithString("output_format", mcp.DefaultString("png"), mcp.Enum("png", "jpg"), mcp.Description("Optional. Output image format: 'png' (default, lossless) or 'jpg'. An extension in output_filename overrides this.")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'frame.png'). The client-provided extension is honored, selects the output format, and overrides output_format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated using output_format. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output file (e.g., 'frame.png').")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output file to (uses GENMEDIA_BUCKET if set and this is empty).")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegExtractFrameHandler(ctx, request, cfg)
	})
}

// ffmpegExtractFrameHandler is the handler for the 'ffmpeg_extract_frame' tool. It
// prepares the input, verifies it has a video stream, resolves the extraction mode and
// (for at_timestamp) validates the timestamp against the input's actual duration, then
// extracts a single still image. The output format defaults to PNG unless overridden by
// output_format or an extension on output_filename.
func ffmpegExtractFrameHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_extract_frame")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_extract_frame", argsMap)

	inputMediaURI, _ := argsMap["input_media_uri"].(string)
	if strings.TrimSpace(inputMediaURI) == "" {
		return mcp.NewToolResultError("Parameter 'input_media_uri' is required."), nil
	}

	mode, _ := argsMap["mode"].(string)
	mode = strings.TrimSpace(mode)
	if mode == "" {
		mode = extractModeLastFrame
	}
	if mode != extractModeLastFrame && mode != extractModeAtTimestamp {
		return mcp.NewToolResultError(fmt.Sprintf("Parameter 'mode' must be '%s' or '%s'.", extractModeLastFrame, extractModeAtTimestamp)), nil
	}

	timestampSeconds, hasTimestamp := argsMap["timestamp"].(float64)
	if mode == extractModeAtTimestamp {
		if !hasTimestamp {
			return mcp.NewToolResultError("Parameter 'timestamp' is required (in seconds) when mode is 'at_timestamp'."), nil
		}
		if timestampSeconds < 0 {
			return mcp.NewToolResultError("Parameter 'timestamp' must not be negative."), nil
		}
	}

	// Resolve the output format: an extension on output_filename wins over output_format,
	// which itself defaults to png.
	outputFormat, _ := argsMap["output_format"].(string)
	outputFormat = strings.ToLower(strings.TrimSpace(outputFormat))
	if outputFormat == "" {
		outputFormat = "png"
	}
	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputExt := outputFormat
	if outputFileName != "" {
		if userExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(outputFileName), ".")); userExt != "" {
			outputExt = userExt
		}
	}

	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_extract_frame: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}

	span.SetAttributes(
		attribute.String("input_media_uri", inputMediaURI),
		attribute.String("mode", mode),
		attribute.Float64("timestamp", timestampSeconds),
		attribute.String("output_format", outputExt),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputMedia, inputCleanup, err := common.PrepareInputFile(ctx, inputMediaURI, "extract_frame_input", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input media: %v", err)), nil
	}
	defer inputCleanup()

	streamInfo, err := probeMediaStreamInfo(ctx, localInputMedia)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("Failed to inspect input media: %v", err)), nil
	}
	if !streamInfo.HasVideo {
		return mcp.NewToolResultError("The input has no video stream to extract a frame from."), nil
	}

	// For at_timestamp, validate the requested time against the file's actual duration
	// when it can be determined. If the duration is unknown (some streams don't report
	// one), skip validation and let ffmpeg handle it rather than rejecting a valid request.
	if mode == extractModeAtTimestamp {
		if mediaDuration, probeErr := probeMediaDurationSeconds(ctx, localInputMedia); probeErr != nil {
			log.Printf("Handler ffmpeg_extract_frame: could not determine input duration, skipping timestamp validation: %v", probeErr)
		} else if timestampSeconds >= mediaDuration {
			return mcp.NewToolResultError(fmt.Sprintf("Parameter 'timestamp' (%.3fs) is at or beyond the input's duration (%.3fs).", timestampSeconds, mediaDuration)), nil
		}
	}

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, outputExt)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	if ffmpegErr := executeExtractFrame(ctx, localInputMedia, tempOutputFile, mode, timestampSeconds); ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg frame extraction failed: %v", ffmpegErr)), nil
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	switch mode {
	case extractModeAtTimestamp:
		messageParts = append(messageParts, fmt.Sprintf("Extracted frame at %.3fs as %s in %v.", timestampSeconds, strings.ToUpper(outputExt), duration))
	default:
		messageParts = append(messageParts, fmt.Sprintf("Extracted last frame as %s in %v.", strings.ToUpper(outputExt), duration))
	}
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" && (outputGCSBucket == "" || finalGCSPath == "") {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addNormalizeLoudnessTool defines and registers the 'ffmpeg_normalize_loudness' tool.
// It performs EBU R128 loudness normalization on any audio (or audio-containing video)
// file using the accurate two-pass loudnorm method.
func addNormalizeLoudnessTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_normalize_loudness",
		mcp.WithDescription("Normalizes the perceived loudness of an audio file (or the audio track of a video file) to a target level using EBU R128 loudness normalization. "+
			"This uses the accurate two-pass method: a first pass measures the input's actual integrated loudness, true peak, loudness range and threshold, and a second pass applies a linear correction toward the target using those measurements. This is more accurate than a single-pass normalize and avoids over- or under-correction. "+
			"Useful for levelling recordings or generated speech so that quiet inputs are brought up and loud inputs are brought down to a consistent playback loudness. "+
			"Defaults target -16 LUFS integrated loudness, -1.5 dBTP true peak and 11 LU loudness range, which suit streaming and web playback; all three can be overridden. When the input is a video its video stream is copied unchanged and only the audio is normalized. Fails if the input has no audio stream."),
		mcp.WithString("input_media_uri", mcp.Required(), mcp.Description("URI of the input audio or video file (local path or gs://). Must contain an audio stream.")),
		mcp.WithNumber("target_loudness", mcp.DefaultNumber(defaultTargetLoudnessLUFS), mcp.Description("Optional. Target integrated loudness in LUFS (EBU R128 'I'). Defaults to -16 (common for streaming/web/podcast). Use -23 for EBU R128 broadcast delivery. Valid range: -70 to -5.")),
		mcp.WithNumber("target_true_peak", mcp.DefaultNumber(defaultTargetTruePeakDBTP), mcp.Description("Optional. Maximum true peak in dBTP (loudnorm 'TP'). Defaults to -1.5. Valid range: -9 to 0.")),
		mcp.WithNumber("target_loudness_range", mcp.DefaultNumber(defaultTargetLoudnessRangeLU), mcp.Description("Optional. Target loudness range in LU (loudnorm 'LRA'). Defaults to 11. Valid range: 1 to 50.")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'normalized.wav'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated and the input's extension is preserved. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output file (e.g., 'normalized.wav').")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output file to (uses GENMEDIA_BUCKET if set and this is empty).")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegNormalizeLoudnessHandler(ctx, request, cfg)
	})
}

// ffmpegNormalizeLoudnessHandler is the handler for the 'ffmpeg_normalize_loudness'
// tool. It prepares the input, verifies it has an audio stream, resolves the target
// loudness parameters (falling back to sensible defaults), runs the two-pass EBU R128
// normalization and writes the result to the requested destination.
func ffmpegNormalizeLoudnessHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_normalize_loudness")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_normalize_loudness", argsMap)

	inputMediaURI, _ := argsMap["input_media_uri"].(string)
	if strings.TrimSpace(inputMediaURI) == "" {
		return mcp.NewToolResultError("Parameter 'input_media_uri' is required."), nil
	}

	target := loudnormTarget{
		IntegratedLUFS:  defaultTargetLoudnessLUFS,
		TruePeakDBTP:    defaultTargetTruePeakDBTP,
		LoudnessRangeLU: defaultTargetLoudnessRangeLU,
	}
	if v, ok := argsMap["target_loudness"].(float64); ok {
		target.IntegratedLUFS = v
	}
	if v, ok := argsMap["target_true_peak"].(float64); ok {
		target.TruePeakDBTP = v
	}
	if v, ok := argsMap["target_loudness_range"].(float64); ok {
		target.LoudnessRangeLU = v
	}

	if target.IntegratedLUFS < -70 || target.IntegratedLUFS > -5 {
		return mcp.NewToolResultError("Parameter 'target_loudness' must be between -70 and -5 LUFS."), nil
	}
	if target.TruePeakDBTP < -9 || target.TruePeakDBTP > 0 {
		return mcp.NewToolResultError("Parameter 'target_true_peak' must be between -9 and 0 dBTP."), nil
	}
	if target.LoudnessRangeLU < 1 || target.LoudnessRangeLU > 50 {
		return mcp.NewToolResultError("Parameter 'target_loudness_range' must be between 1 and 50 LU."), nil
	}

	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_normalize_loudness: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}

	span.SetAttributes(
		attribute.String("input_media_uri", inputMediaURI),
		attribute.Float64("target_loudness", target.IntegratedLUFS),
		attribute.Float64("target_true_peak", target.TruePeakDBTP),
		attribute.Float64("target_loudness_range", target.LoudnessRangeLU),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputMedia, inputCleanup, err := common.PrepareInputFile(ctx, inputMediaURI, "loudnorm_input", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input media: %v", err)), nil
	}
	defer inputCleanup()

	streamInfo, err := probeMediaStreamInfo(ctx, localInputMedia)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("Failed to inspect input media: %v", err)), nil
	}
	if !streamInfo.HasAudio {
		return mcp.NewToolResultError("The input has no audio stream to normalize."), nil
	}

	// Preserve the input's container by default so the output format is predictable;
	// a client-provided output filename extension overrides it.
	defaultOutputExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(localInputMedia), "."))
	if defaultOutputExt == "" {
		if streamInfo.HasVideo {
			defaultOutputExt = "mp4"
		} else {
			defaultOutputExt = "wav"
		}
	}
	if outputFileName != "" {
		if userExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(outputFileName), ".")); userExt != "" {
			defaultOutputExt = userExt
		}
	}

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, defaultOutputExt)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	measurements, ffmpegErr := executeNormalizeLoudness(ctx, localInputMedia, tempOutputFile, target, streamInfo.HasVideo, streamInfo.SampleRate)
	if ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg loudness normalization failed: %v", ffmpegErr)), nil
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Loudness normalization to %s LUFS (measured input loudness %s LUFS, true peak %s dBTP) completed in %v.",
		formatLoudnormValue(target.IntegratedLUFS), measurements.InputI, measurements.InputTP, duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" && (outputGCSBucket == "" || finalGCSPath == "") {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addResizeReframeTool defines and registers the 'ffmpeg_resize_reframe' tool. It
// resizes an image or video to a target geometry and reconciles any aspect-ratio
// mismatch by padding (letterbox/pillarbox, the default) or cropping.
func addResizeReframeTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_resize_reframe",
		mcp.WithDescription("Resizes and reframes an image OR a video to a target geometry. A single image is treated as a one-frame stream, so the same tool handles both. "+
			"Specify the target either as an explicit width and/or height in pixels, or as an aspect-ratio shorthand ('16:9', '9:16', '1:1'); the aspect_ratio can be combined with a single width or height (the other side is computed), or used alone (the input's width is kept). Providing both width and height sets the exact frame and ignores aspect_ratio. "+
			"When the source and target aspect ratios differ, the mismatch is reconciled by 'reframe_mode': 'pad' (default) scales the whole picture to fit and fills the remainder with bars (letterbox/pillarbox), preserving all content; 'crop' scales to fill the frame edge-to-edge and trims the overflow. Pad is the default because it never discards picture content. "+
			"Target dimensions are automatically rounded to even numbers, which many video codecs require. Works on local paths and gs:// URIs and preserves any audio stream unchanged."),
		mcp.WithString("input_media_uri", mcp.Required(), mcp.Description("URI of the input image or video file (local path or gs://). Must contain a visual (image or video) stream.")),
		mcp.WithNumber("width", mcp.Description("Optional. Target width in pixels (must be positive). Combine with 'height' for an exact frame, with 'aspect_ratio' to compute the height, or alone for a proportional resize that keeps the input's aspect ratio.")),
		mcp.WithNumber("height", mcp.Description("Optional. Target height in pixels (must be positive). Combine with 'width' for an exact frame, with 'aspect_ratio' to compute the width, or alone for a proportional resize that keeps the input's aspect ratio.")),
		mcp.WithString("aspect_ratio", mcp.Description("Optional. Target aspect ratio shorthand in W:H form (e.g. '16:9', '9:16', '1:1'). Used with a single width or height to size the frame, or alone to reframe at the input's width. Ignored when both width and height are given.")),
		mcp.WithString("reframe_mode", mcp.DefaultString(defaultReframeMode), mcp.Description("Optional. How to handle an aspect-ratio mismatch: 'pad' (default) keeps the whole frame and adds bars; 'crop' fills the frame and cuts off the excess.")),
		mcp.WithString("pad_color", mcp.DefaultString(defaultPadColor), mcp.Description("Optional. Fill colour for the bars added in 'pad' mode (e.g. 'black', 'white', '#000000', '0xFFFFFF'). Defaults to black. Ignored in 'crop' mode.")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'reframed.mp4' or 'thumb.png'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated and the input's extension is preserved. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output file.")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output file to (uses GENMEDIA_BUCKET if set and this is empty).")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegResizeReframeHandler(ctx, request, cfg)
	})
}

// ffmpegResizeReframeHandler is the handler for the 'ffmpeg_resize_reframe' tool. It
// validates the requested target geometry, probes the input's visual dimensions
// (rejecting inputs with no image/video stream), resolves the final even target
// width/height, and runs the scale+pad/crop filtergraph, writing the result to the
// requested destination.
func ffmpegResizeReframeHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_resize_reframe")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_resize_reframe", argsMap)

	inputMediaURI, _ := argsMap["input_media_uri"].(string)
	if strings.TrimSpace(inputMediaURI) == "" {
		return mcp.NewToolResultError("Parameter 'input_media_uri' is required."), nil
	}

	// Resolve the requested target components. Numbers arrive as float64 from JSON;
	// 0 is used internally to mean "not supplied", so a supplied zero or negative
	// dimension is an explicit error.
	var reqWidth, reqHeight int
	if v, ok := argsMap["width"].(float64); ok {
		if v <= 0 {
			return mcp.NewToolResultError("Parameter 'width' must be a positive number of pixels."), nil
		}
		reqWidth = int(math.Round(v))
	}
	if v, ok := argsMap["height"].(float64); ok {
		if v <= 0 {
			return mcp.NewToolResultError("Parameter 'height' must be a positive number of pixels."), nil
		}
		reqHeight = int(math.Round(v))
	}

	var aspect float64
	if raw, ok := argsMap["aspect_ratio"].(string); ok && strings.TrimSpace(raw) != "" {
		aspect, err = parseAspectRatio(raw)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Parameter 'aspect_ratio' is invalid: %v", err)), nil
		}
	}

	if reqWidth == 0 && reqHeight == 0 && aspect == 0 {
		return mcp.NewToolResultError("Provide at least one of 'width', 'height', or 'aspect_ratio' to define the target."), nil
	}

	reframeMode := defaultReframeMode
	if raw, ok := argsMap["reframe_mode"].(string); ok && strings.TrimSpace(raw) != "" {
		reframeMode = strings.ToLower(strings.TrimSpace(raw))
	}
	if reframeMode != reframeModePad && reframeMode != reframeModeCrop {
		return mcp.NewToolResultError(fmt.Sprintf("Parameter 'reframe_mode' must be %q or %q.", reframeModePad, reframeModeCrop)), nil
	}

	padColor := defaultPadColor
	if raw, ok := argsMap["pad_color"].(string); ok && strings.TrimSpace(raw) != "" {
		padColor = strings.TrimSpace(raw)
	}
	if !isValidPadColor(padColor) {
		return mcp.NewToolResultError("Parameter 'pad_color' must be a simple colour name or hex value (e.g. 'black', '#000000', '0xFFFFFF')."), nil
	}

	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_resize_reframe: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}

	span.SetAttributes(
		attribute.String("input_media_uri", inputMediaURI),
		attribute.Int("requested_width", reqWidth),
		attribute.Int("requested_height", reqHeight),
		attribute.Float64("aspect_ratio", aspect),
		attribute.String("reframe_mode", reframeMode),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputMedia, inputCleanup, err := common.PrepareInputFile(ctx, inputMediaURI, "resize_input", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input media: %v", err)), nil
	}
	defer inputCleanup()

	// A single ffprobe call yields both the input's dimensions and whether it carries
	// an audio stream (used to decide if audio is stream-copied through the resize).
	streamInfo, err := probeMediaStreamInfo(ctx, localInputMedia)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("Cannot resize this input: %v", err)), nil
	}
	if streamInfo.Width <= 0 || streamInfo.Height <= 0 {
		return mcp.NewToolResultError("Cannot resize this input: it has no video or image stream with usable dimensions"), nil
	}
	inWidth, inHeight := streamInfo.Width, streamInfo.Height
	hasAudio := streamInfo.HasAudio

	targetWidth, targetHeight, err := resolveTargetDimensions(reqWidth, reqHeight, aspect, inWidth, inHeight)
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("Could not resolve target dimensions: %v", err)), nil
	}
	span.SetAttributes(
		attribute.Int("target_width", targetWidth),
		attribute.Int("target_height", targetHeight),
	)

	// Preserve the input's container/extension by default; a client-provided output
	// filename extension overrides it and selects the output format.
	defaultOutputExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(localInputMedia), "."))
	if defaultOutputExt == "" {
		defaultOutputExt = "mp4"
	}
	if outputFileName != "" {
		if userExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(outputFileName), ".")); userExt != "" {
			defaultOutputExt = userExt
		}
	}

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, defaultOutputExt)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	target := reframeTarget{Width: targetWidth, Height: targetHeight, Mode: reframeMode, PadColor: padColor}
	if ffmpegErr := executeResizeReframe(ctx, localInputMedia, tempOutputFile, target, hasAudio); ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg resize/reframe failed: %v", ffmpegErr)), nil
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Resized from %dx%d to %dx%d (%s mode) in %v.",
		inWidth, inHeight, targetWidth, targetHeight, reframeMode, duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" && (outputGCSBucket == "" || finalGCSPath == "") {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addAdjustVolumeTool defines and registers the 'ffmpeg_adjust_volume' tool.
// This tool allows for changing the volume of an audio file by a specified decibel (dB) level.
func addAdjustVolumeTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_adjust_volume",
		mcp.WithDescription("Adjusts the volume of an audio file by a specified dB amount."),
		mcp.WithString("input_audio_uri", mcp.Required(), mcp.Description("URI of the input audio file (local path or gs://).")),
		mcp.WithNumber("volume_db_change", mcp.Required(), mcp.Description("Volume change in dB (e.g., -10 for -10dB, 5 for +5dB).")),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output audio file. The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output audio file.")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output audio file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output audio file to.")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegAdjustVolumeHandler(ctx, request, cfg)
	})
}

// ffmpegAdjustVolumeHandler is the handler for the volume adjustment tool.
// It applies a volume change to the input audio file using FFmpeg's volume filter.
func ffmpegAdjustVolumeHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_adjust_volume")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_adjust_volume", argsMap)

	inputAudioURI, _ := argsMap["input_audio_uri"].(string)
	volumeDBChangeFloat, paramOK := argsMap["volume_db_change"].(float64)
	if !paramOK {
		return mcp.NewToolResultError("Parameter 'volume_db_change' is required and must be a number."), nil
	}
	volumeDBChange := int(volumeDBChangeFloat)
	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_adjust_volume: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}
	if inputAudioURI == "" {
		return mcp.NewToolResultError("Parameter 'input_audio_uri' is required."), nil
	}

	span.SetAttributes(
		attribute.String("input_audio_uri", inputAudioURI),
		attribute.Int("volume_db_change", volumeDBChange),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	localInputAudio, inputCleanup, err := common.PrepareInputFile(ctx, inputAudioURI, "input_audio_vol", cfg.ProjectID)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input audio: %v", err)), nil
	}
	defer inputCleanup()

	defaultOutputExt := "mp3"
	inputExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(localInputAudio), "."))
	if inputExt != "" {
		switch inputExt {
		case "wav", "mp3", "aac", "m4a", "ogg", "flac":
			defaultOutputExt = inputExt
		}
	}
	if outputFileName != "" {
		userExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(outputFileName), "."))
		if userExt != "" {
			defaultOutputExt = userExt
		}
	}

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, defaultOutputExt)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	volumeFilter := fmt.Sprintf("volume=%ddB", volumeDBChange)
	_, ffmpegErr := runFFmpegCommand(ctx, "-y", "-i", localInputAudio, "-af", volumeFilter, tempOutputFile)
	if ffmpegErr != nil {
		span.RecordError(ffmpegErr)
		return mcp.NewToolResultError(fmt.Sprintf("FFMpeg adjust volume failed: %v", ffmpegErr)), nil
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Volume adjustment (%ddB) completed in %v.", volumeDBChange, duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" && (outputGCSBucket == "" || finalGCSPath == "") {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}

// addLayerAudioTool defines and registers the 'ffmpeg_layer_audio_files' tool.
// This tool is used to mix (layer) multiple audio files together into a single audio stream.
func addLayerAudioTool(s *server.MCPServer, cfg *common.Config) {
	tool := mcp.NewTool("ffmpeg_layer_audio_files",
		mcp.WithDescription("Layers multiple audio files together (mixing)."),
		mcp.WithArray("input_audio_uris", mcp.Required(), mcp.Description("Array of URIs for the input audio files to layer (local paths or gs://)."), mcp.Items(map[string]any{"type": "string"})),
		mcp.WithString("output_filename", mcp.Description("Optional. Desired name for the output file (e.g., 'layered_audio.mp3'). The client-provided extension is honored and selects the output format. Takes precedence over the deprecated output_file_name. If omitted, a unique name is generated. An existing file of the same name is overwritten.")),
		mcp.WithString("output_file_name", mcp.Description("Optional (deprecated; use output_filename). Desired name for the output mixed audio file (e.g., 'layered_audio.mp3').")),
		mcp.WithString("output_local_dir", mcp.Description("Optional. Local directory to save the output file.")),
		mcp.WithString("output_gcs_bucket", mcp.Description("Optional. GCS bucket to upload the output file to.")),
	)
	s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return ffmpegLayerAudioHandler(ctx, request, cfg)
	})

	s.AddPrompt(mcp.NewPrompt("create-gif",
		mcp.WithPromptDescription("Creates a GIF from a video file."),
		mcp.WithArgument("input_video_uri", mcp.ArgumentDescription("The URI of the video file to convert."), mcp.RequiredArgument()),
		mcp.WithArgument("fps", mcp.ArgumentDescription("Frames per second for the output GIF.")),
		mcp.WithArgument("scale_width_factor", mcp.ArgumentDescription("Factor to scale the input video's width by.")),
	), func(ctx context.Context, request mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
		inputURI, ok := request.Params.Arguments["input_video_uri"]
		if !ok || strings.TrimSpace(inputURI) == "" {
			return mcp.NewGetPromptResult(
				"Missing Input URI",
				[]mcp.PromptMessage{
					mcp.NewPromptMessage(mcp.RoleAssistant, mcp.NewTextContent("What video file (local path or gs:// URI) would you like to convert to a GIF?")),
				},
			), nil
		}

		// Call the existing handler logic
		args := make(map[string]interface{}, len(request.Params.Arguments))
		for k, v := range request.Params.Arguments {
			args[k] = v
		}
		toolRequest := mcp.CallToolRequest{
			Params: mcp.CallToolParams{Arguments: args},
		}
		result, err := ffmpegVideoToGifHandler(ctx, toolRequest, cfg)
		if err != nil {
			return nil, err
		}

		var responseText string
		for _, content := range result.Content {
			if textContent, ok := content.(mcp.TextContent); ok {
				responseText += textContent.Text + "\n"
			}
		}

		return mcp.NewGetPromptResult(
			"GIF Creation Result",
			[]mcp.PromptMessage{
				mcp.NewPromptMessage(mcp.RoleAssistant, mcp.NewTextContent(strings.TrimSpace(responseText))),
			},
		), nil
	})
}

// ffmpegLayerAudioHandler is the handler for the audio layering tool.
// It takes multiple audio inputs and uses FFmpeg's amix filter to merge them into a single output file.
func ffmpegLayerAudioHandler(ctx context.Context, request mcp.CallToolRequest, cfg *common.Config) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "ffmpeg_layer_audio_files")
	defer span.End()

	startTime := time.Now()
	argsMap, err := getArguments(request)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(err.Error()), nil
	}
	log.Printf("Handling %s request with arguments: %v", "ffmpeg_layer_audio_files", argsMap)

	inputAudioURIsRaw, _ := argsMap["input_audio_uris"].([]interface{})
	var inputAudioURIs []string
	for _, item := range inputAudioURIsRaw {
		if strItem, ok := item.(string); ok {
			inputAudioURIs = append(inputAudioURIs, strItem)
		}
	}

	outputFileName := resolveAVToolOutputFilename(argsMap)
	outputLocalDir, _ := argsMap["output_local_dir"].(string)
	outputGCSBucket, _ := argsMap["output_gcs_bucket"].(string)
	outputGCSBucket = strings.TrimSpace(outputGCSBucket)

	if outputGCSBucket == "" && cfg.GenmediaBucket != "" {
		outputGCSBucket = cfg.GenmediaBucket
		log.Printf("Handler ffmpeg_layer_audio_files: 'output_gcs_bucket' parameter not provided, using default from GENMEDIA_BUCKET: %s", outputGCSBucket)
	}
	if outputGCSBucket != "" {
		outputGCSBucket = strings.TrimPrefix(outputGCSBucket, "gs://")
	}
	if len(inputAudioURIs) < 1 {
		if len(inputAudioURIs) == 0 {
			return mcp.NewToolResultError("At least one audio file is required for layering."), nil
		}
		log.Println("Warning: Only one input file provided for layering. The 'layering' will essentially be a copy or re-encode of this single file.")
	}

	span.SetAttributes(
		attribute.StringSlice("input_audio_uris", inputAudioURIs),
		attribute.String("output_file_name", outputFileName),
		attribute.String("output_local_dir", outputLocalDir),
		attribute.String("output_gcs_bucket", outputGCSBucket),
	)

	var localInputFiles []string
	var inputCleanups []func()
	defer func() {
		for _, c := range inputCleanups {
			c()
		}
	}()

	var ffmpegInputArgs []string
	for i, uri := range inputAudioURIs {
		localPath, cleanup, errPrep := common.PrepareInputFile(ctx, uri, fmt.Sprintf("layer_input_%d", i), cfg.ProjectID)
		if errPrep != nil {
			span.RecordError(errPrep)
			return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare input audio file %s: %v", uri, errPrep)), nil
		}
		inputCleanups = append(inputCleanups, cleanup)
		localInputFiles = append(localInputFiles, localPath)
		ffmpegInputArgs = append(ffmpegInputArgs, "-i", localPath)
	}

	defaultOutputExt := "mp3"
	if len(localInputFiles) > 0 {
		firstExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(localInputFiles[0]), "."))
		if firstExt == "wav" || firstExt == "mp3" || firstExt == "aac" || firstExt == "m4a" {
			defaultOutputExt = firstExt
		}
	}
	if outputFileName != "" {
		userExt := strings.ToLower(strings.TrimPrefix(filepath.Ext(outputFileName), "."))
		if userExt != "" {
			defaultOutputExt = userExt
		}
	}

	tempOutputFile, finalOutputFilename, outputCleanup, err := common.HandleOutputPreparation(outputFileName, defaultOutputExt)
	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to prepare output file: %v", err)), nil
	}
	defer outputCleanup()

	var commandArgs []string
	commandArgs = append(commandArgs, "-y")
	commandArgs = append(commandArgs, ffmpegInputArgs...)

	if len(localInputFiles) > 1 {
		amixFilter := fmt.Sprintf("amix=inputs=%d:duration=longest", len(localInputFiles))
		commandArgs = append(commandArgs, "-filter_complex", amixFilter, tempOutputFile)
	} else if len(localInputFiles) == 1 {
		commandArgs = append(commandArgs, "-c:a", "copy", tempOutputFile)
		log.Println("Layering with single input: attempting codec copy. FFMpeg may re-encode if necessary for container.")
	} else {
		return mcp.NewToolResultError("No input files for layering."), nil
	}

	_, ffmpegErr := runFFmpegCommand(ctx, commandArgs...)
	if ffmpegErr != nil {
		if len(localInputFiles) == 1 && strings.Contains(ffmpegErr.Error(), "could not find tag for codec") || strings.Contains(ffmpegErr.Error(), "does not support stream copying") {
			log.Printf("Codec copy failed for single file layering, attempting re-encode. Original error: %v", ffmpegErr)
			var reencodeArgs []string
			reencodeArgs = append(reencodeArgs, "-y", "-i", localInputFiles[0])
			if defaultOutputExt == "wav" {
				reencodeArgs = append(reencodeArgs, "-c:a", "pcm_s16le", tempOutputFile)
			} else {
				reencodeArgs = append(reencodeArgs, "-c:a", "aac", "-b:a", "192k", tempOutputFile)
			}
			_, ffmpegErr = runFFmpegCommand(ctx, reencodeArgs...)
		}
		if ffmpegErr != nil {
			span.RecordError(ffmpegErr)
			return mcp.NewToolResultError(fmt.Sprintf("FFMpeg audio layering failed: %v", ffmpegErr)), nil
		}
	}

	finalLocalPath, finalGCSPath, processErr := common.ProcessOutputAfterFFmpeg(ctx, tempOutputFile, finalOutputFilename, outputLocalDir, outputGCSBucket, cfg.ProjectID)
	if processErr != nil {
		span.RecordError(processErr)
		return mcp.NewToolResultError(fmt.Sprintf("Failed to process FFMpeg output: %v", processErr)), nil
	}

	duration := time.Since(startTime)
	span.SetAttributes(attribute.Float64("duration_ms", float64(duration.Milliseconds())))

	var messageParts []string
	messageParts = append(messageParts, fmt.Sprintf("Audio layering of %d files completed in %v.", len(localInputFiles), duration))
	if outputLocalDir != "" && finalLocalPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output saved locally to: %s.", finalLocalPath))
	} else if finalLocalPath != "" && (outputGCSBucket == "" || finalGCSPath == "") {
		messageParts = append(messageParts, fmt.Sprintf("Temporary output was at: %s (cleaned up if not moved/uploaded).", finalLocalPath))
	}
	if finalGCSPath != "" {
		messageParts = append(messageParts, fmt.Sprintf("Output uploaded to GCS: %s.", finalGCSPath))
	}
	if len(messageParts) == 1 {
		messageParts = append(messageParts, "No specific output location requested beyond temporary processing.")
	}
	return mcp.NewToolResultText(strings.Join(messageParts, " ")), nil
}
