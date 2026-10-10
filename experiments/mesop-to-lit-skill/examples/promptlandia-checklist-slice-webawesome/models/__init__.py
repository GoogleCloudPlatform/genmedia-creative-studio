# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The `models` package contains the domain models, parsers, and prompt templates
used across the application.

The generation logic itself lives in the `services` package (see
`services.llm_client.LLMClient` and the `services.improver` / `services.checklist`
/ `services.trimmer` modules). Importing this package therefore has no side
effects and does not require any environment configuration.
"""
