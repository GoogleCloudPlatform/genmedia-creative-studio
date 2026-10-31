// Copyright 2025 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package cmd

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"cloud.google.com/go/firestore"
	"cloud.google.com/go/storage"
	"github.com/charmbracelet/bubbles/table"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/spf13/cobra"
	"google.golang.org/api/iterator"
)

// Supported CSV manifest presets for the ingest subcommand.
const (
	CSVPresetGeneric     = "generic"
	CSVPresetBatchPrompt = "batch-prompt"
	CSVPresetVTOModels   = "vto-models"
	CSVPresetVTOCatalog  = "vto-catalog"
)

type gcsMediaObject struct {
	ID            string    `json:"id"`
	Bucket        string    `json:"bucket"`
	ObjectName    string    `json:"object_name"`
	GCSURI        string    `json:"gcs_uri"`
	MimeType      string    `json:"mime_type"`
	MediaCategory string    `json:"media_type"`
	SizeBytes     int64     `json:"size_bytes"`
	Updated       time.Time `json:"updated"`
	Prompt        string    `json:"prompt"`
	Model         string    `json:"model"`
}

type ingestOptions struct {
	MediaType  string
	View       string
	CSVPreset  string
	OutputFile string
	Register   bool
	DryRun     bool
	UserEmail  string
	Model      string
	Mode       string
	Prompt     string
	ModelGroup string
	Limit      int
}

var ingestCmd = &cobra.Command{
	Use:     "ingest [gs://bucket/prefix]",
	GroupID: GroupMutate,
	Short:   "Scan a GCS bucket prefix to generate batch CSV manifests or register Firestore MediaItems",
	Long: `Scans a Google Cloud Storage (GCS) bucket and optional object prefix for media
assets (images, videos, audio), automatically generating deterministic document
IDs and either:

  1. Exporting a workflow-ready CSV or JSON manifest (--view=csv, --csv-preset=generic|batch-prompt|vto-models|vto-catalog)
     for Gemini / Nano Banana batch processing or Shop the Look VTO workflows, and/or
  2. Bulk-registering the discovered GCS objects directly into the GenMedia Creative Studio
     Firestore collection (--register) as MediaItem documents so they immediately appear
     in the Library UI without manual one-by-one uploads.

Document IDs are derived deterministically from the canonical gs:// URI
(gcs_<16-hex-sha256>), making repeated '--register' runs idempotent.`,
	Example: `  # Generate a batch CSV manifest of all images under a GCS prefix
  genmedia ingest gs://my-campaign-bucket/summer-shoot/ --media-type=image --view=csv > batch_images.csv

  # Generate a Shop the Look VTO models CSV directly from a GCS folder
  genmedia ingest gs://my-campaign-bucket/vto-models/ --csv-preset=vto-models --output=vto_models.csv

  # Preview Firestore MediaItem registration without writing (--dry-run)
  genmedia ingest gs://my-campaign-bucket/summer-shoot/ --register --dry-run --json

  # Bulk-register existing GCS assets into the GMCS Firestore library
  genmedia ingest gs://my-campaign-bucket/summer-shoot/ --register --user-email=alice@example.com`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		bucket, prefix, err := parseGCSURI(args[0])
		if err != nil {
			return err
		}

		rawView, _ := cmd.Flags().GetString("view")
		opts := ingestOptions{
			View: resolveEffectiveView(cmd, rawView),
		}
		opts.MediaType, _ = cmd.Flags().GetString("media-type")
		opts.CSVPreset, _ = cmd.Flags().GetString("csv-preset")
		opts.OutputFile, _ = cmd.Flags().GetString("output")
		opts.Register, _ = cmd.Flags().GetBool("register")
		opts.DryRun, _ = cmd.Flags().GetBool("dry-run")
		opts.UserEmail, _ = cmd.Flags().GetString("user-email")
		opts.Model, _ = cmd.Flags().GetString("model")
		opts.Mode, _ = cmd.Flags().GetString("mode")
		opts.Prompt, _ = cmd.Flags().GetString("prompt")
		opts.ModelGroup, _ = cmd.Flags().GetString("model-group")
		opts.Limit, _ = cmd.Flags().GetInt("limit")

		if opts.UserEmail == "" {
			opts.UserEmail = firstNonEmptyEnv("USER_EMAIL", "USER")
		}
		if opts.Model == "" {
			opts.Model = "external-ingest"
		}
		if opts.Mode == "" {
			opts.Mode = "ingested"
		}
		if opts.ModelGroup == "" {
			opts.ModelGroup = "casual"
		}

		if _, _, presetErr := buildIngestCSV(nil, opts.CSVPreset, opts); presetErr != nil {
			return presetErr
		}

		ctx := cmd.Context()
		items, err := scanGCSMediaObjects(ctx, bucket, prefix, opts)
		if err != nil {
			return err
		}

		if opts.Register && !opts.DryRun {
			if err := registerMediaItemsInFirestore(ctx, items, opts); err != nil {
				return err
			}
		}

		return renderIngestOutput(items, opts)
	},
}

func init() {
	rootCmd.AddCommand(ingestCmd)
	ingestCmd.Flags().StringP("media-type", "m", "", "Filter discovered objects by media type: 'image', 'video', or 'audio' (empty for all media)")
	ingestCmd.Flags().StringP("view", "v", "csv", "Output format: 'csv', 'json', 'table', or 'text'")
	ingestCmd.Flags().String("csv-preset", CSVPresetGeneric, "CSV schema preset: 'generic', 'batch-prompt', 'vto-models', or 'vto-catalog'")
	ingestCmd.Flags().StringP("output", "o", "", "Write CSV/JSON manifest to a file path instead of stdout")
	ingestCmd.Flags().Bool("register", false, "Bulk-register discovered GCS objects as MediaItem documents in Firestore")
	ingestCmd.Flags().Bool("dry-run", false, "Preview ingested items and Firestore MediaItem payloads without writing to Firestore")
	ingestCmd.Flags().String("user-email", "", "Owner email to stamp on registered Firestore MediaItem documents (defaults to USER_EMAIL or USER)")
	ingestCmd.Flags().String("model", "external-ingest", "Model name to stamp on registered Firestore MediaItem documents")
	ingestCmd.Flags().String("mode", "ingested", "Workflow mode to stamp on registered Firestore MediaItem documents")
	ingestCmd.Flags().String("prompt", "", "Default prompt to associate with ingested assets (defaults to humanized filename)")
	ingestCmd.Flags().String("model-group", "casual", "Default model_group when using --csv-preset=vto-models or vto-catalog")
	ingestCmd.Flags().IntP("limit", "n", 0, "Maximum number of GCS objects to ingest (0 for all)")
}

// parseGCSURI extracts the bucket name and optional object prefix from a gs://bucket/prefix URI.
func parseGCSURI(rawURI string) (bucket, prefix string, err error) {
	trimmed := strings.TrimSpace(rawURI)
	if trimmed == "" {
		return "", "", errors.New("GCS URI must not be empty (Hint: pass gs://<bucket>/<optional-prefix>)")
	}
	trimmed = strings.TrimPrefix(trimmed, "gs://")
	trimmed = strings.TrimPrefix(trimmed, "/")
	if trimmed == "" {
		return "", "", fmt.Errorf("invalid GCS URI %q: bucket name is required", rawURI)
	}
	if strings.Contains(trimmed, "..") {
		return "", "", fmt.Errorf("invalid GCS URI %q: must not contain '..' path segments", rawURI)
	}

	bucket, prefix, hasSlash := strings.Cut(trimmed, "/")
	if bucket == "" || !validResourceRe.MatchString(bucket) {
		return "", "", fmt.Errorf("invalid GCS bucket name %q in URI %q", bucket, rawURI)
	}
	if hasSlash {
		prefix = strings.TrimLeft(prefix, "/")
	}
	return bucket, prefix, nil
}

// inferMediaMimeType resolves the canonical MIME type and top-level category ("image", "video", "audio")
// from an object's name and GCS Content-Type attribute.
func inferMediaMimeType(objectName, contentType string) (mimeType, mediaCategory string, ok bool) {
	ext := strings.ToLower(path.Ext(objectName))
	switch ext {
	case ".png":
		return "image/png", "image", true
	case ".jpg", ".jpeg":
		return "image/jpeg", "image", true
	case ".webp":
		return "image/webp", "image", true
	case ".gif":
		return "image/gif", "image", true
	case ".mp4":
		return "video/mp4", "video", true
	case ".mov":
		return "video/quicktime", "video", true
	case ".webm":
		return "video/webm", "video", true
	case ".wav":
		return "audio/wav", "audio", true
	case ".mp3":
		return "audio/mpeg", "audio", true
	case ".ogg":
		return "audio/ogg", "audio", true
	case ".flac":
		return "audio/flac", "audio", true
	}

	normalizedCT := strings.ToLower(strings.TrimSpace(strings.Split(contentType, ";")[0]))
	for _, cat := range []string{"image", "video", "audio"} {
		if strings.HasPrefix(normalizedCT, cat+"/") {
			return normalizedCT, cat, true
		}
	}
	return "", "", false
}

// deterministicMediaDocID returns a collision-resistant, Firestore-safe document ID for a gs:// URI.
func deterministicMediaDocID(gcsURI string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(gcsURI)))
	return "gcs_" + hex.EncodeToString(sum[:8])
}

// humanizeObjectPrompt derives a human-readable prompt/description from an object path when overridePrompt is empty.
func humanizeObjectPrompt(objectName, overridePrompt string) string {
	if trimmed := strings.TrimSpace(overridePrompt); trimmed != "" {
		return trimmed
	}
	base := path.Base(objectName)
	stem := strings.TrimSuffix(base, path.Ext(base))
	replacer := strings.NewReplacer("_", " ", "-", " ")
	cleaned := strings.TrimSpace(replacer.Replace(stem))
	if cleaned == "" {
		return base
	}
	return cleaned
}

// buildIngestedMediaItem constructs a Firestore document map compatible with GMCS Core's MediaItem dataclass.
func buildIngestedMediaItem(item gcsMediaObject, opts ingestOptions) map[string]any {
	ts := item.Updated
	if ts.IsZero() {
		ts = time.Now().UTC()
	}
	modelName := opts.Model
	if modelName == "" {
		modelName = "external-ingest"
	}
	mode := opts.Mode
	if mode == "" {
		mode = "ingested"
	}
	prompt := humanizeObjectPrompt(item.ObjectName, opts.Prompt)

	doc := map[string]any{
		"id":              item.ID,
		"status":          "complete",
		"user_email":      opts.UserEmail,
		"timestamp":       ts,
		"prompt":          prompt,
		"original_prompt": prompt,
		"model":           modelName,
		"mime_type":       item.MimeType,
		"media_type":      item.MediaCategory,
		"mode":            mode,
		"gcsuri":          item.GCSURI,
		"gcs_uris":        []string{item.GCSURI},
		"comment":         fmt.Sprintf("Ingested from gs://%s/%s", item.Bucket, item.ObjectName),
	}
	if item.MediaCategory == "image" {
		doc["num_images"] = 1
	}
	return doc
}

// buildIngestCSV formats discovered GCS media objects using the requested CSV preset.
func buildIngestCSV(items []gcsMediaObject, preset string, opts ingestOptions) (headers []string, rows [][]string, err error) {
	normalized := strings.ToLower(strings.TrimSpace(preset))
	if normalized == "" {
		normalized = CSVPresetGeneric
	}
	modelGroup := opts.ModelGroup
	if modelGroup == "" {
		modelGroup = "casual"
	}

	switch normalized {
	case CSVPresetGeneric:
		headers = []string{"id", "gcs_uri", "mime_type", "media_type", "size_bytes", "updated", "prompt", "model"}
		rows = make([][]string, len(items))
		for i, item := range items {
			var updatedStr string
			if !item.Updated.IsZero() {
				updatedStr = item.Updated.UTC().Format(time.RFC3339)
			}
			rows[i] = []string{
				item.ID,
				item.GCSURI,
				item.MimeType,
				item.MediaCategory,
				strconv.FormatInt(item.SizeBytes, 10),
				updatedStr,
				item.Prompt,
				item.Model,
			}
		}
		return headers, rows, nil

	case CSVPresetBatchPrompt:
		headers = []string{"gcs_uri", "media_type", "mime_type", "prompt"}
		rows = make([][]string, len(items))
		for i, item := range items {
			rows[i] = []string{
				item.GCSURI,
				item.MediaCategory,
				item.MimeType,
				item.Prompt,
			}
		}
		return headers, rows, nil

	case CSVPresetVTOModels:
		// Matches models/shop_the_look_workflow.py required_fields for VTO models.
		headers = []string{
			"model_group",
			"model_id",
			"model_name",
			"model_description",
			"model_view",
			"primary_view",
			"model_image",
		}
		rows = make([][]string, len(items))
		for i, item := range items {
			rows[i] = []string{
				modelGroup,
				fmt.Sprintf("model_%d", i+1),
				item.Prompt,
				item.Prompt,
				"front",
				"true",
				item.GCSURI,
			}
		}
		return headers, rows, nil

	case CSVPresetVTOCatalog:
		// Matches models/shop_the_look_workflow.py required_fields for VTO catalog items.
		headers = []string{
			"item_id",
			"look_id",
			"article_type",
			"article_color",
			"model_group",
			"description",
			"image_view",
			"try_on_order",
		}
		rows = make([][]string, len(items))
		for i, item := range items {
			rows[i] = []string{
				fmt.Sprintf("item_%d", i+1),
				strconv.Itoa(i + 1),
				"top",
				"default",
				modelGroup,
				item.Prompt,
				item.GCSURI,
				"1",
			}
		}
		return headers, rows, nil

	default:
		return nil, nil, fmt.Errorf("invalid --csv-preset %q: choose %q, %q, %q, or %q",
			preset, CSVPresetGeneric, CSVPresetBatchPrompt, CSVPresetVTOModels, CSVPresetVTOCatalog)
	}
}

func scanGCSMediaObjects(ctx context.Context, bucket, prefix string, opts ingestOptions) ([]gcsMediaObject, error) {
	storageClient, err := storage.NewClient(ctx)
	if err != nil {
		return nil, fmt.Errorf("creating GCS client: %w (Hint: run 'gcloud auth application-default login')", err)
	}
	defer func() { _ = storageClient.Close() }()

	query := &storage.Query{Prefix: prefix}
	iter := storageClient.Bucket(bucket).Objects(ctx, query)

	var items []gcsMediaObject
	for {
		attrs, err := iter.Next()
		if errors.Is(err, iterator.Done) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("listing objects in gs://%s/%s: %w", bucket, prefix, err)
		}
		if strings.HasSuffix(attrs.Name, "/") {
			continue
		}

		mimeType, mediaCategory, ok := inferMediaMimeType(attrs.Name, attrs.ContentType)
		if !ok {
			continue
		}
		if opts.MediaType != "" && !strings.EqualFold(opts.MediaType, mediaCategory) {
			continue
		}

		gcsURI := fmt.Sprintf("gs://%s/%s", bucket, attrs.Name)
		items = append(items, gcsMediaObject{
			ID:            deterministicMediaDocID(gcsURI),
			Bucket:        bucket,
			ObjectName:    attrs.Name,
			GCSURI:        gcsURI,
			MimeType:      mimeType,
			MediaCategory: mediaCategory,
			SizeBytes:     attrs.Size,
			Updated:       attrs.Updated,
			Prompt:        humanizeObjectPrompt(attrs.Name, opts.Prompt),
			Model:         opts.Model,
		})

		if opts.Limit > 0 && len(items) >= opts.Limit {
			break
		}
	}
	return items, nil
}

func registerMediaItemsInFirestore(ctx context.Context, items []gcsMediaObject, opts ingestOptions) error {
	if len(items) == 0 {
		return nil
	}
	client, err := NewFirestoreClient(ctx, projectID, databaseID)
	if err != nil {
		return fmt.Errorf("creating Firestore client for --register: %w", err)
	}
	defer func() { _ = client.Close() }()

	col := client.Collection(collectionName)
	bulkWriter := client.BulkWriter(ctx)
	for _, item := range items {
		docData := buildIngestedMediaItem(item, opts)
		docRef := col.Doc(item.ID)
		if _, err := bulkWriter.Set(docRef, docData, firestore.MergeAll); err != nil {
			bulkWriter.End()
			return fmt.Errorf("queueing Firestore write for %q: %w", item.ID, err)
		}
	}
	bulkWriter.Flush()
	bulkWriter.End()
	return nil
}

func renderIngestOutput(items []gcsMediaObject, opts ingestOptions) error {
	outWriter := io.Writer(os.Stdout)
	if opts.OutputFile != "" {
		cleanPath := filepath.Clean(opts.OutputFile)
		f, err := os.Create(cleanPath)
		if err != nil {
			return fmt.Errorf("creating output file %q: %w", cleanPath, err)
		}
		defer func() { _ = f.Close() }()
		outWriter = f
	}

	switch opts.View {
	case "json":
		if opts.Register || opts.DryRun {
			docs := make([]map[string]any, len(items))
			for i, item := range items {
				docs[i] = buildIngestedMediaItem(item, opts)
			}
			payload := map[string]any{
				"count":      len(items),
				"registered": opts.Register && !opts.DryRun,
				"dry_run":    opts.DryRun,
				"collection": collectionName,
				"items":      docs,
			}
			return writeJSON(outWriter, payload)
		}
		return writeJSON(outWriter, items)

	case "csv":
		headers, rows, err := buildIngestCSV(items, opts.CSVPreset, opts)
		if err != nil {
			return err
		}
		return writeCSV(outWriter, headers, rows)

	case "text":
		for _, item := range items {
			_, _ = fmt.Fprintf(outWriter, "ID: %s, GCS_URI: %s, MimeType: %s, Size: %d, Prompt: %s\n",
				item.ID, item.GCSURI, item.MimeType, item.SizeBytes, item.Prompt)
		}
		if opts.Register {
			status := "Registered"
			if opts.DryRun {
				status = "[dry-run] Would register"
			}
			_, _ = fmt.Fprintf(outWriter, "%s %d MediaItem documents in Firestore collection %q.\n", status, len(items), collectionName)
		}
		return nil

	case "table":
		columns := []table.Column{
			{Title: "ID", Width: 22},
			{Title: "MEDIA_TYPE", Width: 12},
			{Title: "MIME_TYPE", Width: 16},
			{Title: "GCS_URI", Width: 55},
			{Title: "PROMPT", Width: 30},
		}
		rows := make([]table.Row, len(items))
		for i, item := range items {
			rows[i] = table.Row{
				item.ID,
				item.MediaCategory,
				item.MimeType,
				item.GCSURI,
				formatFieldValue(item.Prompt, 30),
			}
		}
		t := newStyledTable(columns, rows, 20)
		vp := viewport.New(120, 30)
		m := model{table: t, viewport: vp, showTable: true, commandName: "ingest"}
		if _, err := tea.NewProgram(m).Run(); err != nil {
			return fmt.Errorf("running ingest table view: %w", err)
		}
		return nil

	default:
		return fmt.Errorf("invalid view format %q: choose \"csv\", \"json\", \"table\", or \"text\"", opts.View)
	}
}
