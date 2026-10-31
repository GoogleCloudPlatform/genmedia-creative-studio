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

var addCmd = &cobra.Command{
	Use:     "add",
	GroupID: GroupMutate,
	Short:   "Create a new document in the Firestore collection",
	Long: `Adds a new document to the configured Firestore collection from an inline JSON
string (--data). Pass --dry-run to validate and preview the JSON payload without
writing to Firestore.`,
	Example: `  # Add a new document from inline JSON
  genmedia add --data='{"model":"veo-3.1-fast-generate-001","mime_type":"video/mp4","prompt":"ocean waves"}'

  # Validate and preview the document payload without writing to Firestore
  genmedia add --data='{"model":"imagen-4.0-generate-001","mime_type":"image/png"}' --dry-run`,
	RunE: func(cmd *cobra.Command, args []string) error {
		payload, err := cmd.Flags().GetString("data")
		if err != nil {
			return fmt.Errorf("reading --data flag: %w", err)
		}
		if payload == "" {
			return errors.New("the --data flag is required (Hint: pass --data='{\"model\":\"...\"}')")
		}
		dryRun, _ := cmd.Flags().GetBool("dry-run")

		var jsonData map[string]any
		if err := json.Unmarshal([]byte(payload), &jsonData); err != nil {
			return fmt.Errorf("unmarshaling JSON payload: %w", err)
		}

		if dryRun {
			return emitMutationResult(cmd, map[string]any{
				"action":     "add",
				"dry_run":    true,
				"collection": collectionName,
				"document":   jsonData,
			}, fmt.Sprintf("[dry-run] Would add document to collection %q", collectionName))
		}

		ctx := cmd.Context()
		firestoreClient, err := NewFirestoreClient(ctx, projectID, databaseID)
		if err != nil {
			return fmt.Errorf("creating Firestore client: %w", err)
		}
		defer func() { _ = firestoreClient.Close() }()

		collection := firestoreClient.Collection(collectionName)
		return addDocument(ctx, cmd, collection, jsonData)
	},
}

func addDocument(ctx context.Context, cmd *cobra.Command, collection *firestore.CollectionRef, jsonData map[string]any) error {
	docRef, _, err := collection.Add(ctx, jsonData)
	if err != nil {
		return fmt.Errorf("adding document to collection %q: %w", collection.ID, err)
	}
	return emitMutationResult(cmd, map[string]any{
		"action":     "add",
		"collection": collection.ID,
		"id":         docRef.ID,
	}, PassStyle.Render(fmt.Sprintf("Successfully added document with ID: %s", docRef.ID)))
}

func emitMutationResult(cmd *cobra.Command, payload map[string]any, humanMessage string) error {
	if resolveEffectiveView(cmd, "text") == "json" {
		return writeJSON(os.Stdout, payload)
	}
	fmt.Println(humanMessage)
	return nil
}

func init() {
	rootCmd.AddCommand(addCmd)
	addCmd.Flags().String("data", "", "JSON payload for the new document (required)")
	addCmd.Flags().Bool("dry-run", false, "Validate and preview the document without writing to Firestore")
	_ = addCmd.MarkFlagRequired("data")
}
