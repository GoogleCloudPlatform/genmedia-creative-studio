// Package common provides shared utilities for the MCP Genmedia servers.

package common

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
)

// ShortID returns a 10-character lowercase alphanumeric identifier backed by
// crypto/rand for collision-resistant default filenames.
func ShortID() string {
	return strings.ToLower(rand.Text()[:10])
}

// PrepareInputFile handles the logic for making a file available locally for processing.
// It checks if the given file URI is a GCS path (gs://...) or a local path.
// If it's a GCS path, it downloads the file to a temporary local directory.
// If it's a local path, it verifies that the file exists.
// It returns the local path to the file and a cleanup function to remove any temporary files.
func PrepareInputFile(ctx context.Context, fileURI, purpose string, gcpProjectID string) (localPath string, cleanupFunc func(), err error) {
	cleanupFunc = func() {}

	if strings.HasPrefix(fileURI, "gs://") {
		if gcpProjectID == "" {
			return "", cleanupFunc, errors.New("GOOGLE_CLOUD_PROJECT not set, cannot download from GCS")
		}
		tempDir, errMkdir := os.MkdirTemp("", "input_")
		if errMkdir != nil {
			return "", cleanupFunc, fmt.Errorf("failed to create temp dir for GCS download: %w", errMkdir)
		}

		base := filepath.Base(fileURI)
		if base == "." || base == "/" {
			base = fmt.Sprintf("gcs_download_%s_%s", purpose, ShortID())
		}
		localPath = filepath.Join(tempDir, base)

		log.Printf("Downloading GCS file %s to temporary path %s for %s", fileURI, localPath, purpose)

		gcsErr := DownloadFromGCS(ctx, fileURI, localPath)
		if gcsErr != nil {
			_ = os.RemoveAll(tempDir)
			return "", cleanupFunc, fmt.Errorf("failed to download %s from GCS: %w", fileURI, gcsErr)
		}

		cleanupFunc = func() {
			log.Printf("Cleaning up temporary directory for GCS download: %s", tempDir)
			_ = os.RemoveAll(tempDir)
		}
		return localPath, cleanupFunc, nil
	}

	if _, statErr := os.Stat(fileURI); os.IsNotExist(statErr) {
		return "", cleanupFunc, fmt.Errorf("local input file %s does not exist for %s", fileURI, purpose)
	}
	log.Printf("Using local input file %s for %s", fileURI, purpose)
	return fileURI, cleanupFunc, nil
}

// HandleOutputPreparation creates a temporary directory for FFmpeg output and determines the final output filename.
// If a desired filename is provided, it uses that; otherwise, it generates a unique filename.
// It ensures the filename has the correct extension.
// It returns the full path to the temporary output file, the final filename, and a cleanup function.
func HandleOutputPreparation(desiredOutputFilename, defaultExt string) (tempLocalOutputFile string, finalOutputFilename string, cleanupFunc func(), err error) {
	cleanupFunc = func() {}

	tempDir, errMkdir := os.MkdirTemp("", "output_")
	if errMkdir != nil {
		return "", "", cleanupFunc, fmt.Errorf("failed to create temp dir for FFMpeg output: %w", errMkdir)
	}

	finalOutputFilename = desiredOutputFilename
	if finalOutputFilename == "" {
		finalOutputFilename = fmt.Sprintf("ffmpeg_output_%s.%s", ShortID(), defaultExt)
	} else {
		currentExt := filepath.Ext(finalOutputFilename)
		if currentExt == "" {
			finalOutputFilename = finalOutputFilename + "." + defaultExt
		} else if strings.ToLower(currentExt) != "."+strings.ToLower(defaultExt) {
			log.Printf("Warning: output_file_name '%s' has extension '%s', but expected '%s'. Using original extension.", desiredOutputFilename, currentExt, defaultExt)
		}
	}

	tempLocalOutputFile = filepath.Join(tempDir, finalOutputFilename)

	cleanupFunc = func() {
		log.Printf("Cleaning up temporary output directory: %s", tempDir)
		_ = os.RemoveAll(tempDir)
	}

	log.Printf("FFMpeg will write temporary output to: %s", tempLocalOutputFile)
	log.Printf("Final output filename will be: %s", finalOutputFilename)
	return tempLocalOutputFile, finalOutputFilename, cleanupFunc, nil
}

// ProcessOutputAfterFFmpeg manages the file after it has been processed by FFmpeg.
// It can move the file to a specified local directory and/or upload it to a GCS bucket.
// It returns the final local path and the GCS path of the file.
func ProcessOutputAfterFFmpeg(ctx context.Context, ffmpegOutputActualPath, finalOutputFilename, outputLocalDir, outputGCSBucket string, gcpProjectID string) (finalLocalPath string, finalGCSPath string, err error) {
	currentLocalPath := ffmpegOutputActualPath

	if outputLocalDir != "" {
		// Confine the caller-supplied output directory to the configured output
		// root before any filesystem operation (CWE-22 directory traversal). This
		// rejects absolute paths and ".." escapes; see ResolveConfinedOutputDir.
		confinedDir, confErr := ResolveConfinedOutputDir(outputLocalDir)
		if confErr != nil {
			return "", "", fmt.Errorf("invalid output local directory: %w", confErr)
		}
		outputLocalDir = confinedDir
		if errMkdir := os.MkdirAll(outputLocalDir, 0755); errMkdir != nil {
			return "", "", fmt.Errorf("failed to create specified output local directory %s: %w", outputLocalDir, errMkdir)
		}
		destLocalPath := filepath.Join(outputLocalDir, finalOutputFilename)
		// Collision policy: overwrite with a warning (design #842 §4e).
		if _, statErr := os.Stat(destLocalPath); statErr == nil {
			log.Printf("Warning: output file %q already exists in %s; overwriting (collision policy).", finalOutputFilename, outputLocalDir)
		}
		log.Printf("Moving FFMpeg output from %s to %s", currentLocalPath, destLocalPath)
		if errRename := os.Rename(currentLocalPath, destLocalPath); errRename != nil {
			// If rename fails (e.g. different devices), try copy then remove original
			log.Printf("Rename failed (%v), attempting copy and remove for %s to %s", errRename, currentLocalPath, destLocalPath)
			inputBytes, readErr := os.ReadFile(currentLocalPath)
			if readErr != nil {
				return "", "", fmt.Errorf("failed to read source for copy %s: %w", currentLocalPath, readErr)
			}
			if writeErr := os.WriteFile(destLocalPath, inputBytes, 0644); writeErr != nil {
				return "", "", fmt.Errorf("failed to write destination for copy %s: %w", destLocalPath, writeErr)
			}
			if removeErr := os.Remove(currentLocalPath); removeErr != nil {
				log.Printf("Warning: failed to remove original file %s after copy: %v", currentLocalPath, removeErr)
				// Not returning error here as the file is copied, but log it.
			}
		}
		currentLocalPath = destLocalPath
		finalLocalPath = currentLocalPath
		log.Printf("Output saved to local directory: %s", finalLocalPath)
	} else {
		finalLocalPath = ffmpegOutputActualPath
		log.Printf("Output generated at temporary location: %s (will be cleaned up if not moved or uploaded)", finalLocalPath)
	}

	if outputGCSBucket != "" {
		if gcpProjectID == "" {
			return finalLocalPath, "", errors.New("GOOGLE_CLOUD_PROJECT not set, cannot upload to GCS")
		}
		if _, errStat := os.Stat(currentLocalPath); os.IsNotExist(errStat) {
			return finalLocalPath, "", fmt.Errorf("ffmpeg output file %s not found for GCS upload", currentLocalPath)
		}

		log.Printf("Uploading %s to GCS bucket %s as object %s", currentLocalPath, outputGCSBucket, finalOutputFilename)

		fileData, readErr := os.ReadFile(currentLocalPath)
		if readErr != nil {
			return finalLocalPath, "", fmt.Errorf("failed to read file %s for GCS upload: %w", currentLocalPath, readErr)
		}

		contentType := "" // uploadToGCS will infer it

		errUpload := UploadToGCS(ctx, outputGCSBucket, finalOutputFilename, contentType, fileData)
		if errUpload != nil {
			return finalLocalPath, "", fmt.Errorf("failed to upload to GCS (gs://%s/%s): %w", outputGCSBucket, finalOutputFilename, errUpload)
		}
		finalGCSPath = fmt.Sprintf("gs://%s/%s", outputGCSBucket, finalOutputFilename)
		log.Printf("Output uploaded to GCS: %s", finalGCSPath)
	}
	return finalLocalPath, finalGCSPath, nil
}

// GetTail returns the last n lines of a string.
func GetTail(s string, n int) string {
	lines := strings.Split(s, "\n")
	if len(lines) <= n {
		return s
	}
	return strings.Join(lines[len(lines)-n:], "\n")
}

// FormatBytes converts a size in bytes to a more human-readable format (e.g., KB, MB, GB).
// This is useful for logging file sizes in a way that is easy to understand.
func FormatBytes(bytes int64) string {
	const unit = 1024
	if bytes < unit {
		return fmt.Sprintf("%d B", bytes)
	}
	div, exp := int64(unit), 0
	for n := bytes / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(bytes)/float64(div), "KMGTPE"[exp])
}

// NormalizeImageMIMEType returns a usable image MIME type for generated image
// bytes when the model response omits one.
func NormalizeImageMIMEType(mimeType string) string {
	mimeType = strings.ToLower(strings.TrimSpace(mimeType))
	if mimeType == "" {
		return "image/png"
	}
	return mimeType
}

// ImageExtensionForMIMEType returns a suitable file extension for known image
// MIME types and defaults to png.
func ImageExtensionForMIMEType(mimeType string) string {
	switch NormalizeImageMIMEType(mimeType) {
	case "image/jpeg":
		return ".jpg"
	case "image/webp":
		return ".webp"
	case "image/gif":
		return ".gif"
	default:
		return ".png"
	}
}
