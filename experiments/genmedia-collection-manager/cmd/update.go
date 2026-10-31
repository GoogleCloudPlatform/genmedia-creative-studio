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
	"encoding/json"
	"errors"
	"fmt"
	"os"

	"cloud.google.com/go/firestore"
	"github.com/spf13/cobra"
)

var updateCmd = &cobra.Command{
	Use:     "update [DOCUMENT_ID]",
	GroupID: GroupMutate,
	Short:   "Merge-update a document in the Firestore collection by ID",
	Long: `Updates an existing document in the configured Firestore collection by its ID
using inline JSON (--data) or a JSON file (--data-file). Fields are merged into
the existing document via firestore.MergeAll. Pass --dry-run to preview changes.`,
	Example: `  # Merge-update a document with inline JSON
  genmedia update abc123xyz --data='{"rewritten_prompt":"calm ocean waves at sunset"}'

  # Merge-update a document from a JSON file
  genmedia update abc123xyz --data-file=patch.json

  # Preview a document update without writing to Firestore
  genmedia update abc123xyz --data='{"status":"complete"}' --dry-run`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		docID := args[0]
		if err := validateDocID(docID); err != nil {
			return err
		}

		dataFile, _ := cmd.Flags().GetString("data-file")
		payload, _ := cmd.Flags().GetString("data")
		dryRun, _ := cmd.Flags().GetBool("dry-run")

		if err := validateUpdateFlags(payload, dataFile); err != nil {
			return err
		}

		if dataFile != "" {
			fileContent, err := os.ReadFile(dataFile)
			if err != nil {
				return fmt.Errorf("reading data file %q: %w", dataFile, err)
			}
			payload = string(fileContent)
		}

		var jsonData map[string]any
		if err := json.Unmarshal([]byte(payload), &jsonData); err != nil {
			return fmt.Errorf("unmarshaling JSON payload: %w", err)
		}

		if dryRun {
			return emitMutationResult(cmd, map[string]any{
				"action":     "update",
				"dry_run":    true,
				"collection": collectionName,
				"id":         docID,
				"patch":      jsonData,
			}, fmt.Sprintf("[dry-run] Would merge-update document %q in collection %q", docID, collectionName))
		}

		ctx := cmd.Context()
		firestoreClient, err := NewFirestoreClient(ctx, projectID, databaseID)
		if err != nil {
			return fmt.Errorf("creating Firestore client: %w", err)
		}
		defer func() { _ = firestoreClient.Close() }()

		collection := firestoreClient.Collection(collectionName)
		return updateDocument(ctx, cmd, collection, docID, jsonData)
	},
}

func validateUpdateFlags(payload, dataFile string) error {
	if dataFile != "" && payload != "" {
		return errors.New("cannot specify both --data and --data-file")
	}
	if dataFile == "" && payload == "" {
		return errors.New("either --data or --data-file is required")
	}
	return nil
}

func updateDocument(ctx context.Context, cmd *cobra.Command, collection *firestore.CollectionRef, docID string, jsonData map[string]any) error {
	if _, err := collection.Doc(docID).Set(ctx, jsonData, firestore.MergeAll); err != nil {
		return fmt.Errorf("updating document %q: %w", docID, err)
	}
	return emitMutationResult(cmd, map[string]any{
		"action":     "update",
		"collection": collection.ID,
		"id":         docID,
	}, PassStyle.Render(fmt.Sprintf("Successfully updated document: %s", docID)))
}

func init() {
	rootCmd.AddCommand(updateCmd)
	updateCmd.Flags().String("data", "", "Inline JSON fields to merge into the document")
	updateCmd.Flags().StringP("data-file", "F", "", "Path to a JSON file containing fields to merge into the document")
	updateCmd.Flags().Bool("dry-run", false, "Validate and preview the merge patch without writing to Firestore")
}
