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
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var getCmd = &cobra.Command{
	Use:     "get [DOCUMENT_ID]",
	GroupID: GroupBrowse,
	Short:   "Fetch a single Firestore document by ID as JSON",
	Long: `Retrieves and pretty-prints a single document from the configured Firestore
collection by its document ID. Output is always formatted as JSON.`,
	Example: `  # Fetch a single document by ID
  genmedia get abc123xyz

  # Fetch a document from a custom collection
  genmedia get abc123xyz --collection=genmedia_vto_catalog`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		docID := args[0]
		if err := validateDocID(docID); err != nil {
			return err
		}

		ctx := cmd.Context()
		client, err := NewFirestoreClient(ctx, projectID, databaseID)
		if err != nil {
			return fmt.Errorf("creating Firestore client: %w", err)
		}
		defer func() { _ = client.Close() }()

		col := client.Collection(collectionName)
		doc, err := col.Doc(docID).Get(ctx)
		if err != nil {
			return fmt.Errorf("fetching document %q from collection %q: %w", docID, collectionName, err)
		}

		docData := doc.Data()
		docData["id"] = doc.Ref.ID
		return writeJSON(os.Stdout, docData)
	},
}

func init() {
	rootCmd.AddCommand(getCmd)
}
