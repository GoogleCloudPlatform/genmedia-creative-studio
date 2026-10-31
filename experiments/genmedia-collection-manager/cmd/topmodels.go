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
	"cmp"
	"context"
	"fmt"
	"os"
	"slices"
	"strconv"
	"time"

	"cloud.google.com/go/firestore"
	"github.com/charmbracelet/bubbles/table"
	"github.com/spf13/cobra"
)

var topModelsCmd = &cobra.Command{
	Use:     "top-models",
	GroupID: GroupAnalytics,
	Short:   "Aggregate user generation activity grouped by model",
	Long: `Aggregates documents in the configured Firestore collection by generative model
and user email, showing how many assets each user generated per model.`,
	Example: `  # Display per-model usage tables
  genmedia top-models

  # Export model usage breakdown to CSV
  genmedia top-models --view=csv > model_usage.csv

  # Output model usage breakdown as JSON
  genmedia top-models --json`,
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
		return topModels(ctx, col, view, limit)
	},
}

func init() {
	rootCmd.AddCommand(topModelsCmd)
	topModelsCmd.Flags().StringP("view", "v", "table", "Output format: 'table', 'json', 'text', or 'csv'")
	topModelsCmd.Flags().IntP("limit", "n", 0, "Maximum number of models to return (0 for all)")
}

type modelUserStat struct {
	Email        string    `json:"user_email"`
	DocCount     int       `json:"document_count"`
	LastActivity time.Time `json:"latest_timestamp"`
}

type modelStat struct {
	Model    string                    `json:"model"`
	UserDocs map[string]*modelUserStat `json:"users"`
}

func accumulateModelStat(modelStats map[string]*modelStat, docData map[string]any) {
	modelName := stringField(docData, "model")
	if modelName == "" {
		return
	}
	if _, ok := modelStats[modelName]; !ok {
		modelStats[modelName] = &modelStat{
			Model:    modelName,
			UserDocs: make(map[string]*modelUserStat),
		}
	}
	email := stringField(docData, "user_email")
	if email == "" {
		return
	}
	userStat, ok := modelStats[modelName].UserDocs[email]
	if !ok {
		userStat = &modelUserStat{Email: email}
		modelStats[modelName].UserDocs[email] = userStat
	}
	userStat.DocCount++
	if ts := timeField(docData, "timestamp"); ts.After(userStat.LastActivity) {
		userStat.LastActivity = ts
	}
}

func sortedModelUsers(userDocs map[string]*modelUserStat) []*modelUserStat {
	users := make([]*modelUserStat, 0, len(userDocs))
	for _, stat := range userDocs {
		users = append(users, stat)
	}
	slices.SortFunc(users, func(a, b *modelUserStat) int {
		if c := cmp.Compare(b.DocCount, a.DocCount); c != 0 {
			return c
		}
		return cmp.Compare(a.Email, b.Email)
	})
	return users
}

func topModels(ctx context.Context, col *firestore.CollectionRef, view string, limit int) error {
	modelStats := make(map[string]*modelStat)
	processor := func(doc *firestore.DocumentSnapshot) error {
		accumulateModelStat(modelStats, doc.Data())
		return nil
	}

	if err := processDocuments(ctx, col, processor); err != nil {
		return fmt.Errorf("processing documents for top-models: %w", err)
	}

	sortedModels := make([]*modelStat, 0, len(modelStats))
	for _, stat := range modelStats {
		sortedModels = append(sortedModels, stat)
	}
	slices.SortFunc(sortedModels, func(a, b *modelStat) int {
		return cmp.Compare(a.Model, b.Model)
	})
	sortedModels = applyLimit(sortedModels, limit)

	switch view {
	case "json":
		return writeJSON(os.Stdout, sortedModels)
	case "text":
		for _, mStat := range sortedModels {
			fmt.Printf("Model: %s\n", mStat.Model)
			for _, userStat := range sortedModelUsers(mStat.UserDocs) {
				fmt.Printf("  Email: %s, Count: %d, Last Activity: %s\n",
					userStat.Email, userStat.DocCount, userStat.LastActivity.Format(timestampLayout))
			}
		}
	case "csv":
		headers := []string{"MODEL", "USER_EMAIL", "DOCUMENT_COUNT", "LATEST_TIMESTAMP"}
		var csvRows [][]string
		for _, mStat := range sortedModels {
			for _, userStat := range sortedModelUsers(mStat.UserDocs) {
				csvRows = append(csvRows, []string{
					mStat.Model,
					userStat.Email,
					strconv.Itoa(userStat.DocCount),
					userStat.LastActivity.Format(timestampLayout),
				})
			}
		}
		if err := writeCSV(os.Stdout, headers, csvRows); err != nil {
			return err
		}
	case "table":
		columns := []table.Column{
			{Title: "USER_EMAIL", Width: 40},
			{Title: "DOCUMENT_COUNT", Width: 20},
			{Title: "LATEST_TIMESTAMP", Width: 20},
		}

		for _, mStat := range sortedModels {
			fmt.Printf("%s\n", AccentStyle.Render("Model: "+mStat.Model))

			users := sortedModelUsers(mStat.UserDocs)
			rows := make([]table.Row, len(users))
			for i, userStat := range users {
				rows[i] = table.Row{
					userStat.Email,
					strconv.Itoa(userStat.DocCount),
					userStat.LastActivity.Format(timestampLayout),
				}
			}

			t := newStyledTable(columns, rows, 10)
			fmt.Println(baseStyle.Render(t.View()))
		}
	default:
		return fmt.Errorf("invalid view format %q: choose \"table\", \"json\", \"text\", or \"csv\"", view)
	}
	return nil
}
