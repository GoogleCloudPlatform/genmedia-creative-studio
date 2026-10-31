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

	"cloud.google.com/go/firestore"
	"google.golang.org/api/iterator"
)

// processDocuments iterates through all documents in a collection and applies a processor function to each.
func processDocuments(ctx context.Context, col *firestore.CollectionRef, processor func(doc *firestore.DocumentSnapshot) error) error {
	iter := col.Documents(ctx)
	defer iter.Stop()
	for {
		doc, err := iter.Next()
		if errors.Is(err, iterator.Done) {
			break
		}
		if err != nil {
			return fmt.Errorf("iterating documents in collection %q: %w", col.ID, err)
		}
		if err := processor(doc); err != nil {
			return err
		}
	}
	return nil
}
