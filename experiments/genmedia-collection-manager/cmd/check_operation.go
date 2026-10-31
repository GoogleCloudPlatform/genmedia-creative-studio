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
	"os/exec"
	"regexp"
	"strings"

	"github.com/spf13/cobra"
)

var (
	location        string
	validResourceRe = regexp.MustCompile(`^[a-zA-Z0-9._-]+$`)
)

var checkOperationCmd = &cobra.Command{
	Use:     "check-operation [OPERATION_ID]",
	GroupID: GroupOps,
	Short:   "Inspect the status of a long-running Vertex AI operation",
	Long: `Checks the status of a long-running Vertex AI media generation operation
(such as Veo video generation) given its operation ID using the gcloud CLI.`,
	Example: `  # Check an operation in us-central1
  genmedia check-operation 1234567890abcdef --location=us-central1

  # Return operation status as JSON
  genmedia check-operation 1234567890abcdef --json`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		operationID := strings.TrimSpace(args[0])
		if err := validateIdentifier("operation ID", operationID); err != nil {
			return err
		}
		if err := validateIdentifier("location", location); err != nil {
			return err
		}
		if err := validateIdentifier("project ID", projectID); err != nil {
			return err
		}

		fullOperationName := fmt.Sprintf("projects/%s/locations/%s/operations/%s", projectID, location, operationID)
		gcloudArgs := []string{
			"ai", "operations", "describe", fullOperationName,
			"--project=" + projectID,
			"--region=" + location,
		}
		if resolveEffectiveView(cmd, "text") == "json" {
			gcloudArgs = append(gcloudArgs, "--format=json")
		} else {
			fmt.Printf("gcloud %s\n", strings.Join(gcloudArgs, " "))
		}

		output, err := exec.CommandContext(cmd.Context(), "gcloud", gcloudArgs...).CombinedOutput()
		if len(output) > 0 {
			fmt.Print(string(output))
		}
		if err != nil {
			return fmt.Errorf("describing operation %q: %w", fullOperationName, err)
		}
		return nil
	},
}

// validateIdentifier rejects values containing whitespace, flags, or shell/path metacharacters.
func validateIdentifier(label, value string) error {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return fmt.Errorf("%s must not be empty", label)
	}
	if strings.HasPrefix(trimmed, "-") || !validResourceRe.MatchString(trimmed) {
		return fmt.Errorf("invalid %s %q: must contain only alphanumeric characters, '.', '_', or '-'", label, value)
	}
	return nil
}

func init() {
	rootCmd.AddCommand(checkOperationCmd)
	checkOperationCmd.Flags().StringVarP(&location, "location", "l", "us-central1", "Google Cloud location for the Vertex AI operation")
}
