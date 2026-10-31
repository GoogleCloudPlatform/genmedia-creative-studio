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
	tea "github.com/charmbracelet/bubbletea"
	"github.com/spf13/cobra"
)

var topUsersCmd = &cobra.Command{
	Use:     "top-users",
	GroupID: GroupAnalytics,
	Short:   "Aggregate top users by generated asset count",
	Long: `Aggregates documents in the configured Firestore collection by 'user_email',
showing each user's total document count and most recent activity timestamp.
In interactive table mode, press Enter on any user row to drill into their assets.`,
	Example: `  # Open the interactive top-users leaderboard
  genmedia top-users

  # Export the top 10 users to CSV
  genmedia top-users --limit=10 --view=csv > top_users.csv

  # Output user activity statistics as JSON
  genmedia top-users --json`,
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
		return topUsers(ctx, col, view, limit)
	},
}

func init() {
	rootCmd.AddCommand(topUsersCmd)
	topUsersCmd.Flags().StringP("view", "v", "table", "Output format: 'table', 'json', 'text', or 'csv'")
	topUsersCmd.Flags().IntP("limit", "n", 0, "Maximum number of users to return (0 for all)")
}

type topUserStat struct {
	Email        string    `json:"user_email"`
	DocCount     int       `json:"document_count"`
	LastActivity time.Time `json:"latest_timestamp"`
}

func accumulateUserStat(userStats map[string]*topUserStat, docData map[string]any) {
	email := stringField(docData, "user_email")
	if email == "" {
		return
	}
	stat, ok := userStats[email]
	if !ok {
		stat = &topUserStat{Email: email}
		userStats[email] = stat
	}
	stat.DocCount++
	if ts := timeField(docData, "timestamp"); ts.After(stat.LastActivity) {
		stat.LastActivity = ts
	}
}

func topUsers(ctx context.Context, col *firestore.CollectionRef, view string, limit int) error {
	userStats := make(map[string]*topUserStat)
	processor := func(doc *firestore.DocumentSnapshot) error {
		accumulateUserStat(userStats, doc.Data())
		return nil
	}

	if err := processDocuments(ctx, col, processor); err != nil {
		return fmt.Errorf("processing documents for top-users: %w", err)
	}

	sortedUsers := make([]*topUserStat, 0, len(userStats))
	for _, stat := range userStats {
		sortedUsers = append(sortedUsers, stat)
	}

	slices.SortFunc(sortedUsers, func(a, b *topUserStat) int {
		if c := cmp.Compare(b.DocCount, a.DocCount); c != 0 {
			return c
		}
		return cmp.Compare(a.Email, b.Email)
	})
	sortedUsers = applyLimit(sortedUsers, limit)

	switch view {
	case "json":
		return writeJSON(os.Stdout, sortedUsers)
	case "text":
		for _, user := range sortedUsers {
			fmt.Printf("Email: %s, Count: %d, Last Activity: %s\n",
				user.Email, user.DocCount, user.LastActivity.Format(timestampLayout))
		}
	case "csv":
		headers := []string{"USER_EMAIL", "DOCUMENT_COUNT", "LATEST_TIMESTAMP"}
		rows := make([][]string, len(sortedUsers))
		for i, user := range sortedUsers {
			rows[i] = []string{
				user.Email,
				strconv.Itoa(user.DocCount),
				user.LastActivity.Format(timestampLayout),
			}
		}
		if err := writeCSV(os.Stdout, headers, rows); err != nil {
			return err
		}
	case "table":
		columns := []table.Column{
			{Title: "USER_EMAIL", Width: 40},
			{Title: "DOCUMENT_COUNT", Width: 20},
			{Title: "LATEST_TIMESTAMP", Width: 20},
		}

		rows := make([]table.Row, len(sortedUsers))
		for i, user := range sortedUsers {
			rows[i] = table.Row{
				user.Email,
				strconv.Itoa(user.DocCount),
				user.LastActivity.Format(timestampLayout),
			}
		}

		t := newStyledTable(columns, rows, 15)
		m := newTopUsersModel(t, col)

		if _, err := tea.NewProgram(m).Run(); err != nil {
			return fmt.Errorf("running top-users table view: %w", err)
		}
	default:
		return fmt.Errorf("invalid view format %q: choose \"table\", \"json\", \"text\", or \"csv\"", view)
	}
	return nil
}
