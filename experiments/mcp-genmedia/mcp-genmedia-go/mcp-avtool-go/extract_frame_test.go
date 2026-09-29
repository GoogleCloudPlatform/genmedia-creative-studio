package main

import (
	"strings"
	"testing"
)

// TestBuildExtractFrameArgs verifies the ffmpeg argument construction for both
// single-frame extraction modes: last_frame (seek from EOF, keep last decoded frame)
// and at_timestamp (fast input seek, one frame at the given time).
func TestBuildExtractFrameArgs(t *testing.T) {
	t.Run("last_frame seeks from EOF and omits -frames:v so the last decoded frame is kept", func(t *testing.T) {
		got := buildExtractFrameArgs("in.mp4", "out.png", extractModeLastFrame, 0)
		want := []string{"-y", "-sseof", "-3", "-i", "in.mp4", "-update", "1", "-q:v", "2", "out.png"}
		if strings.Join(got, " ") != strings.Join(want, " ") {
			t.Errorf("buildExtractFrameArgs last_frame = %v, want %v", got, want)
		}
		if strings.Contains(strings.Join(got, " "), "-frames:v") {
			t.Errorf("last_frame args must not contain -frames:v (it would grab the first frame of the tail): %v", got)
		}
	})

	t.Run("at_timestamp places -ss before -i and grabs one frame", func(t *testing.T) {
		got := buildExtractFrameArgs("in.mp4", "out.jpg", extractModeAtTimestamp, 1.5)
		want := []string{"-y", "-ss", "1.5", "-i", "in.mp4", "-update", "1", "-frames:v", "1", "-q:v", "2", "out.jpg"}
		if strings.Join(got, " ") != strings.Join(want, " ") {
			t.Errorf("buildExtractFrameArgs at_timestamp = %v, want %v", got, want)
		}
	})

	t.Run("at_timestamp renders integer timestamps without a trailing decimal", func(t *testing.T) {
		got := buildExtractFrameArgs("in.mp4", "out.png", extractModeAtTimestamp, 3)
		want := []string{"-y", "-ss", "3", "-i", "in.mp4", "-update", "1", "-frames:v", "1", "-q:v", "2", "out.png"}
		if strings.Join(got, " ") != strings.Join(want, " ") {
			t.Errorf("buildExtractFrameArgs at_timestamp integer = %v, want %v", got, want)
		}
	})
}
