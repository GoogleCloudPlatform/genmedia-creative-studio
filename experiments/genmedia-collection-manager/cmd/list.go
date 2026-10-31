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
	"fmt"
	"os"
	"strings"

	"cloud.google.com/go/firestore"
	"github.com/charmbracelet/bubbles/table"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/spf13/cobra"
)

var listCmd = &cobra.Command{
	Use:     "list",
	GroupID: GroupBrowse,
	Short:   "Browse and export documents in the Firestore collection",
	Long: `Lists documents in the configured Firestore collection sorted newest first.
By default, launches an interactive Bubble Tea table where pressing Enter opens
the full JSON document in a scrollable viewport. Pass --view=csv or --json to
export records for batch workflows or downstream automation.`,
	Example: `  # Browse all documents in an interactive TUI table
  genmedia list

  # Filter by media type and export GCS URIs to CSV for batch workflows
  genmedia list --media-type=image --fields="id,gcsuri,gcs_uris,mime_type,model,prompt,timestamp" --view=csv > images.csv

  # Return the 20 most recent video records as JSON
  genmedia list --media-type=video --limit=20 --json`,
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		client, err := NewFirestoreClient(ctx, projectID, databaseID)
		if err != nil {
			return fmt.Errorf("creating Firestore client: %w", err)
		}
		defer func() { _ = client.Close() }()

		col := client.Collection(collectionName)
		fields, _ := cmd.Flags().GetString("fields")
		mediaType, _ := cmd.Flags().GetString("media-type")
		rawView, _ := cmd.Flags().GetString("view")
		limit, _ := cmd.Flags().GetInt("limit")
		view := resolveEffectiveView(cmd, rawView)
		return listDocs(ctx, col, fields, mediaType, view, limit)
	},
}

func init() {
	rootCmd.AddCommand(listCmd)
	listCmd.Flags().StringP("fields", "f", "", "Comma-separated list of fields to display (e.g., 'id,gcsuri,gcs_uris,model,prompt,timestamp')")
	listCmd.Flags().StringP("media-type", "m", "", "Filter by media type prefix (e.g., 'video', 'image', 'audio')")
	listCmd.Flags().StringP("view", "v", "table", "Output format: 'table', 'json', 'text', or 'csv'")
	listCmd.Flags().IntP("limit", "n", 0, "Maximum number of documents to return (0 for all)")
}

func resolveFieldsToShow(fields, mediaType string) []string {
	if fields != "" {
		parts := strings.Split(fields, ",")
		fieldsToShow := make([]string, 0, len(parts))
		for _, part := range parts {
			if trimmed := strings.TrimSpace(part); trimmed != "" {
				fieldsToShow = append(fieldsToShow, trimmed)
			}
		}
		if len(fieldsToShow) > 0 {
			return fieldsToShow
		}
	}

	switch mediaType {
	case "image":
		return []string{"id", "mime_type", "user_email", "timestamp", "model", "original_prompt", "rewritten_prompt"}
	case "video":
		return []string{"id", "mime_type", "user_email", "timestamp", "model", "prompt", "duration"}
	case "audio":
		return []string{"id", "mime_type", "user_email", "timestamp", "model", "original_prompt", "prompt"}
	default:
		return []string{"id", "mime_type", "user_email", "timestamp", "model", "prompt"}
	}
}

func listDocs(ctx context.Context, col *firestore.CollectionRef, fields, mediaType, view string, limit int) error {
	fieldsToShow := resolveFieldsToShow(fields, mediaType)

	docs, err := col.Documents(ctx).GetAll()
	if err != nil {
		return fmt.Errorf("fetching documents from collection %q: %w", col.ID, err)
	}

	var results []map[string]any
	for _, doc := range docs {
		docData := doc.Data()
		docData["id"] = doc.Ref.ID

		if mediaType != "" {
			mime := stringField(docData, "mime_type")
			if !strings.HasPrefix(mime, mediaType) {
				continue
			}
		}

		resultData := make(map[string]any, len(fieldsToShow)+1)
		for _, field := range fieldsToShow {
			if val, ok := docData[field]; ok {
				resultData[field] = val
			} else {
				resultData[field] = ""
			}
		}
		if _, hasTimestamp := resultData["timestamp"]; !hasTimestamp {
			if ts, ok := docData["timestamp"]; ok {
				resultData["timestamp"] = ts
			}
		}
		results = append(results, resultData)
	}

	sortMapsByTimestampDesc(results)
	results = applyLimit(results, limit)

	switch view {
	case "json":
		return writeJSON(os.Stdout, results)
	case "text":
		for _, result := range results {
			for i, field := range fieldsToShow {
				fmt.Printf("%s: %v", field, result[field])
				if i < len(fieldsToShow)-1 {
					fmt.Print(", ")
				}
			}
			fmt.Println()
		}
	case "csv":
		csvRows := make([][]string, len(results))
		for i, result := range results {
			row := make([]string, len(fieldsToShow))
			for j, field := range fieldsToShow {
				row[j] = formatFieldValue(result[field], 0)
			}
			csvRows[i] = row
		}
		if err := writeCSV(os.Stdout, fieldsToShow, csvRows); err != nil {
			return err
		}
	case "table":
		columns := make([]table.Column, len(fieldsToShow))
		for i, field := range fieldsToShow {
			width := 25
			if field == "mime_type" {
				width = 12
			}
			columns[i] = table.Column{Title: strings.ToUpper(field), Width: width}
		}

		rows := make([]table.Row, len(results))
		for i, result := range results {
			row := make(table.Row, len(fieldsToShow))
			for j, field := range fieldsToShow {
				row[j] = formatFieldValue(result[field], 50)
			}
			rows[i] = row
		}

		t := newStyledTable(columns, rows, 20)
		vp := viewport.New(120, 30)

		m := model{table: t, viewport: vp, showTable: true, col: col, commandName: "list"}
		if _, err := tea.NewProgram(m).Run(); err != nil {
			return fmt.Errorf("running table view: %w", err)
		}
	default:
		return fmt.Errorf("invalid view format %q: choose \"table\", \"json\", \"text\", or \"csv\"", view)
	}
	return nil
}
