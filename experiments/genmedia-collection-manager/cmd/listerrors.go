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
	"slices"
	"time"

	"cloud.google.com/go/firestore"
	"github.com/charmbracelet/bubbles/table"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/spf13/cobra"
)

var listErrorsCmd = &cobra.Command{
	Use:     "list-errors",
	GroupID: GroupBrowse,
	Short:   "List documents that recorded a generation error",
	Long: `Iterates through documents in the configured Firestore collection and displays
any record with a non-empty 'error_message' field, sorted newest first.`,
	Example: `  # Browse failed generation records in an interactive table
  genmedia list-errors

  # Export failed generation records to CSV for triage
  genmedia list-errors --view=csv > errors.csv

  # Inspect the 10 most recent failures as JSON
  genmedia list-errors --limit=10 --json`,
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := cmd.Context()
		client, err := NewFirestoreClient(ctx, projectID, databaseID)
		if err != nil {
			return fmt.Errorf("creating Firestore client: %w", err)
		}
		defer func() { _ = client.Close() }()

		rawView, _ := cmd.Flags().GetString("view")
		limit, _ := cmd.Flags().GetInt("limit")
		view := resolveEffectiveView(cmd, rawView)
		col := client.Collection(collectionName)
		return listDocsWithErrors(ctx, col, view, limit)
	},
}

func init() {
	rootCmd.AddCommand(listErrorsCmd)
	listErrorsCmd.Flags().StringP("view", "v", "table", "Output format: 'table', 'json', 'text', or 'csv'")
	listErrorsCmd.Flags().IntP("limit", "n", 0, "Maximum number of error documents to return (0 for all)")
}

type errorDoc struct {
	ID           string    `json:"id"`
	MimeType     string    `json:"mime_type"`
	Timestamp    time.Time `json:"timestamp"`
	ErrorMessage string    `json:"error_message"`
	UserEmail    string    `json:"user_email"`
	Model        string    `json:"model"`
}

func extractErrorDoc(id string, docData map[string]any) (errorDoc, bool) {
	errMsg := stringField(docData, "error_message")
	if errMsg == "" {
		return errorDoc{}, false
	}
	return errorDoc{
		ID:           id,
		MimeType:     stringField(docData, "mime_type"),
		Timestamp:    timeField(docData, "timestamp"),
		ErrorMessage: errMsg,
		UserEmail:    stringField(docData, "user_email"),
		Model:        stringField(docData, "model"),
	}, true
}

func listDocsWithErrors(ctx context.Context, col *firestore.CollectionRef, view string, limit int) error {
	docs, err := col.Documents(ctx).GetAll()
	if err != nil {
		return fmt.Errorf("fetching documents from collection %q: %w", col.ID, err)
	}

	var errorDocs []errorDoc
	for _, doc := range docs {
		if ed, ok := extractErrorDoc(doc.Ref.ID, doc.Data()); ok {
			errorDocs = append(errorDocs, ed)
		}
	}

	slices.SortStableFunc(errorDocs, func(a, b errorDoc) int {
		return b.Timestamp.Compare(a.Timestamp)
	})
	errorDocs = applyLimit(errorDocs, limit)

	switch view {
	case "json":
		return writeJSON(os.Stdout, errorDocs)
	case "text":
		for _, ed := range errorDocs {
			fmt.Printf("ID: %s, MimeType: %s, UserEmail: %s, Timestamp: %s, Model: %s, Error: %s\n",
				ed.ID, ed.MimeType, ed.UserEmail, ed.Timestamp.Format(timestampLayout), ed.Model, ed.ErrorMessage)
		}
	case "csv":
		headers := []string{"ID", "MIME_TYPE", "USER_EMAIL", "TIMESTAMP", "MODEL", "ERROR_MESSAGE"}
		rows := make([][]string, len(errorDocs))
		for i, ed := range errorDocs {
			rows[i] = []string{
				ed.ID,
				ed.MimeType,
				ed.UserEmail,
				ed.Timestamp.Format(timestampLayout),
				ed.Model,
				ed.ErrorMessage,
			}
		}
		if err := writeCSV(os.Stdout, headers, rows); err != nil {
			return err
		}
	case "table":
		columns := []table.Column{
			{Title: "ID", Width: 25},
			{Title: "MIME_TYPE", Width: 15},
			{Title: "USER_EMAIL", Width: 25},
			{Title: "TIMESTAMP", Width: 20},
			{Title: "MODEL", Width: 20},
			{Title: "ERROR_MESSAGE", Width: 80},
		}

		rows := make([]table.Row, len(errorDocs))
		for i, ed := range errorDocs {
			rows[i] = table.Row{
				ed.ID,
				ed.MimeType,
				ed.UserEmail,
				ed.Timestamp.Format(timestampLayout),
				ed.Model,
				ed.ErrorMessage,
			}
		}

		t := newStyledTable(columns, rows, 15)
		vp := viewport.New(120, 30)

		m := model{table: t, viewport: vp, showTable: true, col: col, commandName: "list-errors"}
		if _, err := tea.NewProgram(m).Run(); err != nil {
			return fmt.Errorf("running table view: %w", err)
		}
	default:
		return fmt.Errorf("invalid view format %q: choose \"table\", \"json\", \"text\", or \"csv\"", view)
	}
	return nil
}
