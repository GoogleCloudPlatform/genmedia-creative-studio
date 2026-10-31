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

	"cloud.google.com/go/firestore"
	"github.com/spf13/cobra"
)

var deleteCmd = &cobra.Command{
	Use:     "delete",
	GroupID: GroupMutate,
	Short:   "Delete a document from the Firestore collection by ID",
	Long: `Deletes a document from the configured Firestore collection by its document ID
(--id). Pass --dry-run to verify the target document ID without deleting it.`,
	Example: `  # Delete a document by ID
  genmedia delete --id="abc123xyz"

  # Preview deletion without modifying Firestore
  genmedia delete --id="abc123xyz" --dry-run`,
	RunE: func(cmd *cobra.Command, args []string) error {
		docID, err := cmd.Flags().GetString("id")
		if err != nil {
			return fmt.Errorf("reading --id flag: %w", err)
		}
		if err := validateDocID(docID); err != nil {
			return err
		}
		dryRun, _ := cmd.Flags().GetBool("dry-run")

		if dryRun {
			return emitMutationResult(cmd, map[string]any{
				"action":     "delete",
				"dry_run":    true,
				"collection": collectionName,
				"id":         docID,
			}, fmt.Sprintf("[dry-run] Would delete document %q from collection %q", docID, collectionName))
		}

		ctx := cmd.Context()
		client, err := NewFirestoreClient(ctx, projectID, databaseID)
		if err != nil {
			return fmt.Errorf("creating Firestore client: %w", err)
		}
		defer func() { _ = client.Close() }()

		col := client.Collection(collectionName)
		return deleteDoc(ctx, cmd, col, docID)
	},
}

func init() {
	rootCmd.AddCommand(deleteCmd)
	deleteCmd.Flags().StringP("id", "i", "", "ID of the document to delete (required)")
	deleteCmd.Flags().Bool("dry-run", false, "Preview deletion without removing the document from Firestore")
	_ = deleteCmd.MarkFlagRequired("id")
}

func deleteDoc(ctx context.Context, cmd *cobra.Command, col *firestore.CollectionRef, docID string) error {
	if _, err := col.Doc(docID).Delete(ctx); err != nil {
		return fmt.Errorf("deleting document %q from collection %q: %w", docID, col.ID, err)
	}
	return emitMutationResult(cmd, map[string]any{
		"action":     "delete",
		"collection": col.ID,
		"id":         docID,
	}, PassStyle.Render(fmt.Sprintf("Document %s deleted successfully from collection %s.", docID, col.ID)))
}
