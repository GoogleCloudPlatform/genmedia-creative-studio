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

// Package cmd implements the CLI commands and interactive TUI for genmedia-collection-manager.
package cmd

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"
)

// Command group IDs used to organize root help output for humans and agents.
const (
	GroupBrowse    = "browse"
	GroupAnalytics = "analytics"
	GroupMutate    = "mutate"
	GroupOps       = "ops"
)

var (
	projectID      string
	collectionName string
	databaseID     string
	jsonOutput     bool
	noTUI          bool
)

var rootCmd = &cobra.Command{
	Use:   "genmedia",
	Short: "Manage GenMedia Creative Studio collections in Firestore and Cloud Storage",
	Long: `genmedia-collection-manager (genmedia) is an interactive terminal UI (TUI) and
agent-aware command-line interface (CLI) for inspecting, searching, aggregating,
exporting, and bulk-ingesting generative media assets stored in Google Cloud
Firestore and Cloud Storage (GCS).

It supports both rich interactive Bubble Tea tables for human operators and
deterministic JSON/CSV output (--json, --view=csv, --dry-run) for automated
workflows and AI agents.`,
	Example: `  # Launch the interactive TUI document browser
  genmedia list --project-id=my-gcp-project

  # Export image GCS URIs and prompts to CSV for batch workflows
  genmedia list --media-type=image --fields="id,gcsuri,gcs_uris,model,prompt" --view=csv > images.csv

  # Scan a GCS bucket prefix and generate a batch CSV manifest
  genmedia ingest gs://my-asset-bucket/campaign-2026/ --media-type=image --view=csv > batch.csv

  # Bulk-register existing GCS objects into the GMCS Firestore library
  genmedia ingest gs://my-asset-bucket/campaign-2026/ --register --user-email=alice@example.com`,
	SilenceUsage: true,
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		if projectID == "" {
			projectID = firstNonEmptyEnv("PROJECT_ID", "GOOGLE_CLOUD_PROJECT")
		}
		if requiresProjectID(cmd) && projectID == "" {
			return errors.New("project-id is required (Hint: pass --project-id=<gcp-project> or run: export PROJECT_ID=$(gcloud config get-value project))")
		}
		return nil
	},
}

func requiresProjectID(cmd *cobra.Command) bool {
	if cmd == nil {
		return false
	}
	switch cmd.Name() {
	case "help", "completion", "genmedia":
		return false
	case "ingest":
		register, _ := cmd.Flags().GetBool("register")
		return register
	default:
		return true
	}
}

func firstNonEmptyEnv(keys ...string) string {
	for _, k := range keys {
		if v := strings.TrimSpace(os.Getenv(k)); v != "" {
			return v
		}
	}
	return ""
}

// Execute runs the root CLI command and exits with a non-zero status on error.
func Execute() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func init() {
	rootCmd.AddGroup(
		&cobra.Group{ID: GroupBrowse, Title: "Browse & Query Commands:"},
		&cobra.Group{ID: GroupAnalytics, Title: "Analytics Commands:"},
		&cobra.Group{ID: GroupMutate, Title: "Ingest & Mutation Commands:"},
		&cobra.Group{ID: GroupOps, Title: "Operations Commands:"},
	)

	rootCmd.PersistentFlags().StringVarP(&projectID, "project-id", "p", "", "Google Cloud project ID (overrides PROJECT_ID / GOOGLE_CLOUD_PROJECT)")

	defaultCollection := firstNonEmptyEnv("GENMEDIA_COLLECTION", "GENMEDIA_COLLECTION_NAME")
	if defaultCollection == "" {
		defaultCollection = "genmedia"
	}
	rootCmd.PersistentFlags().StringVarP(&collectionName, "collection", "c", defaultCollection, "Firestore collection name (overrides GENMEDIA_COLLECTION)")

	defaultDatabase := firstNonEmptyEnv("GENMEDIA_DATABASE", "GENMEDIA_FIREBASE_DB")
	if defaultDatabase == "(default)" {
		defaultDatabase = ""
	}
	rootCmd.PersistentFlags().StringVarP(&databaseID, "database-id", "d", defaultDatabase, "Firestore database ID (empty for default database; overrides GENMEDIA_DATABASE)")

	rootCmd.PersistentFlags().BoolVar(&jsonOutput, "json", false, "Output results as machine-readable JSON (overrides --view)")
	rootCmd.PersistentFlags().BoolVar(&noTUI, "no-tui", false, "Disable interactive TUI tables and render plain text output (also enabled via GENMEDIA_NO_TUI=1)")

	rootCmd.SetFlagErrorFunc(func(cmd *cobra.Command, err error) error {
		return fmt.Errorf("%w (Hint: run '%s --help' for usage examples)", err, cmd.CommandPath())
	})
}
