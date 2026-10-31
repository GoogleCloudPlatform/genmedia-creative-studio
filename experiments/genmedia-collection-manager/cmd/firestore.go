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
	"errors"
	"fmt"
	"strings"

	"cloud.google.com/go/firestore"
)

// NewFirestoreClient creates a new Firestore client, connecting to a specific database if databaseID is provided.
func NewFirestoreClient(ctx context.Context, projectID, databaseID string) (*firestore.Client, error) {
	if databaseID != "" && databaseID != "(default)" {
		client, err := firestore.NewClientWithDatabase(ctx, projectID, databaseID)
		if err != nil {
			return nil, fmt.Errorf("connecting to Firestore database %q in project %q: %w (Hint: run 'gcloud auth application-default login')", databaseID, projectID, err)
		}
		return client, nil
	}
	client, err := firestore.NewClient(ctx, projectID)
	if err != nil {
		return nil, fmt.Errorf("connecting to default Firestore database in project %q: %w (Hint: run 'gcloud auth application-default login')", projectID, err)
	}
	return client, nil
}

// validateDocID ensures a Firestore document identifier is non-empty and does not contain path separators.
func validateDocID(docID string) error {
	trimmed := strings.TrimSpace(docID)
	if trimmed == "" {
		return errors.New("document ID must not be empty")
	}
	if trimmed == "." || trimmed == ".." || strings.Contains(trimmed, "/") {
		return fmt.Errorf("invalid document ID %q: must not contain '/' or relative path segments", docID)
	}
	return nil
}
