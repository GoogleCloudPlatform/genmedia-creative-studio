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

// Genmedia is a command-line interface (CLI) and interactive TUI for inspecting,
// ingesting, exporting, and managing generative media asset records in Google Cloud
// Firestore and Cloud Storage.
package main

import "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/genmedia-collection-manager/cmd"

func main() {
	cmd.Execute()
}
