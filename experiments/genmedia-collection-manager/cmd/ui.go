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
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"slices"
	"strings"
	"time"

	"cloud.google.com/go/firestore"
	"github.com/charmbracelet/bubbles/table"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/cobra"
	"google.golang.org/api/iterator"
)

const timestampLayout = "2006-01-02 15:04"

// Semantic color palette following Agent-to-Agent (A2A) CLI design guidelines.
var (
	AccentStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("39")).Bold(true)
	CommandStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("250"))
	PassStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("42"))
	WarnStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("214"))
	FailStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("196")).Bold(true)
	MutedStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("240"))
	IDStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("86"))

	baseStyle = lipgloss.NewStyle().
			BorderStyle(lipgloss.NormalBorder()).
			BorderForeground(lipgloss.Color("240"))
)

// resolveEffectiveView returns the output format taking into account --json, --no-tui,
// GENMEDIA_NO_TUI, and NO_COLOR environment overrides.
func resolveEffectiveView(cmd *cobra.Command, requestedView string) string {
	if jsonOutput {
		return "json"
	}
	if cmd != nil {
		if j, err := cmd.Flags().GetBool("json"); err == nil && j {
			return "json"
		}
	}
	view := strings.ToLower(strings.TrimSpace(requestedView))
	if view == "" {
		view = "table"
	}
	if view == "table" && isTUISuppressed(cmd) {
		return "text"
	}
	return view
}

func isTUISuppressed(cmd *cobra.Command) bool {
	if noTUI {
		return true
	}
	if cmd != nil {
		if disabled, err := cmd.Flags().GetBool("no-tui"); err == nil && disabled {
			return true
		}
	}
	if v := strings.TrimSpace(os.Getenv("GENMEDIA_NO_TUI")); v != "" && v != "0" && !strings.EqualFold(v, "false") {
		return true
	}
	return false
}

// applyLimit truncates a slice to at most limit items when limit > 0.
func applyLimit[T any](items []T, limit int) []T {
	if limit <= 0 || len(items) <= limit {
		return items
	}
	return items[:limit]
}

// writeJSON marshals value as indented JSON to w followed by a newline.
func writeJSON(w io.Writer, value any) error {
	formattedJSON, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return fmt.Errorf("marshaling output to JSON: %w", err)
	}
	_, err = fmt.Fprintln(w, string(formattedJSON))
	return err
}

type docFetchedMsg struct {
	header      string
	content     string
	forUserDocs bool
	err         error
}

type model struct {
	table            table.Model
	viewport         viewport.Model
	showTable        bool
	header           string
	width, height    int
	col              *firestore.CollectionRef
	commandName      string
	userDocs         table.Model
	showUserDocs     bool
	showUserDocPager bool
	err              error
}

func (m model) Init() tea.Cmd { return nil }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	case docFetchedMsg:
		if msg.err != nil {
			m.err = msg.err
			return m, nil
		}
		m.header = msg.header
		content := lipgloss.NewStyle().Width(m.viewport.Width).Render(msg.content)
		m.viewport.SetContent(content)
		if msg.forUserDocs {
			m.showUserDocs = false
			m.showUserDocPager = true
		} else {
			m.showTable = false
		}
		return m, nil
	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "enter":
			if m.err != nil || m.col == nil {
				return m, nil
			}
			if m.showUserDocs {
				selectedRow := m.userDocs.SelectedRow()
				if len(selectedRow) == 0 {
					return m, nil
				}
				return m, fetchDocCmd(m.col, selectedRow, true)
			}
			if m.showTable {
				selectedRow := m.table.SelectedRow()
				if len(selectedRow) == 0 {
					return m, nil
				}
				return m, fetchDocCmd(m.col, selectedRow, false)
			}
			return m, nil
		case "esc", "backspace":
			if m.err != nil {
				m.err = nil
				return m, nil
			}
			if m.showUserDocPager {
				m.showUserDocPager = false
				m.showUserDocs = true
			} else if !m.showTable {
				m.showTable = true
				m.showUserDocs = false
			}
			return m, nil
		}
	}

	if m.showUserDocPager {
		m.viewport, cmd = m.viewport.Update(msg)
	} else if m.showUserDocs {
		m.userDocs, cmd = m.userDocs.Update(msg)
	} else if m.showTable {
		m.table, cmd = m.table.Update(msg)
	} else {
		m.viewport, cmd = m.viewport.Update(msg)
	}

	return m, cmd
}

func (m model) View() string {
	if m.err != nil {
		return fmt.Sprintf("%s\n\nPress 'esc' or 'backspace' to return.\n", FailStyle.Render(fmt.Sprintf("Error: %v", m.err)))
	}
	if m.showUserDocPager {
		return fmt.Sprintf("%s\n%s\n", AccentStyle.Render(m.header), baseStyle.Render(m.viewport.View()))
	}
	if m.showUserDocs {
		return fmt.Sprintf("Found %d documents for %s\n%s\n", len(m.userDocs.Rows()), AccentStyle.Render(m.header), baseStyle.Render(m.userDocs.View()))
	}
	if m.showTable {
		return fmt.Sprintf("Found %d documents\n%s\n", len(m.table.Rows()), baseStyle.Render(m.table.View()))
	}
	return fmt.Sprintf("%s\n%s\n", AccentStyle.Render(m.header), baseStyle.Render(m.viewport.View()))
}

func formatRowHeader(row table.Row) string {
	if len(row) == 0 {
		return ""
	}
	if len(row) >= 5 {
		return fmt.Sprintf("Document ID: %s | Mime Type: %s | Model: %s", row[0], row[1], row[4])
	}
	return fmt.Sprintf("Document ID: %s", row[0])
}

func fetchDocCmd(col *firestore.CollectionRef, selectedRow table.Row, forUserDocs bool) tea.Cmd {
	selectedID := selectedRow[0]
	header := formatRowHeader(selectedRow)
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		doc, err := fetchDocument(ctx, col, selectedID)
		if err != nil {
			return docFetchedMsg{err: err}
		}
		prettyJSON, err := json.MarshalIndent(doc, "", "  ")
		if err != nil {
			return docFetchedMsg{err: fmt.Errorf("marshaling document %q: %w", selectedID, err)}
		}
		return docFetchedMsg{
			header:      header,
			content:     string(prettyJSON),
			forUserDocs: forUserDocs,
		}
	}
}

func fetchDocsByUser(ctx context.Context, col *firestore.CollectionRef, userEmail string) ([]map[string]any, error) {
	iter := col.Where("user_email", "==", userEmail).Documents(ctx)
	defer iter.Stop()

	var docs []map[string]any
	for {
		doc, err := iter.Next()
		if errors.Is(err, iterator.Done) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("iterating documents for user %q: %w", userEmail, err)
		}
		data := doc.Data()
		data["id"] = doc.Ref.ID
		docs = append(docs, data)
	}
	sortMapsByTimestampDesc(docs)
	return docs, nil
}

func fetchDocument(ctx context.Context, col *firestore.CollectionRef, docID string) (map[string]any, error) {
	dsnap, err := col.Doc(docID).Get(ctx)
	if err != nil {
		return nil, fmt.Errorf("fetching document %q: %w", docID, err)
	}
	return dsnap.Data(), nil
}

func sortMapsByTimestampDesc(docs []map[string]any) {
	slices.SortStableFunc(docs, func(a, b map[string]any) int {
		aTime := timeField(a, "timestamp")
		bTime := timeField(b, "timestamp")
		return bTime.Compare(aTime)
	})
}

func stringField(data map[string]any, key string) string {
	if val, ok := data[key].(string); ok {
		return val
	}
	return ""
}

func timeField(data map[string]any, key string) time.Time {
	if val, ok := data[key].(time.Time); ok {
		return val
	}
	return time.Time{}
}

func formatFieldValue(val any, maxLen int) string {
	var strVal string
	switch v := val.(type) {
	case time.Time:
		if v.IsZero() {
			return ""
		}
		strVal = v.Format(timestampLayout)
	case string:
		strVal = v
	case []string:
		strVal = strings.Join(v, ";")
	case []any:
		parts := make([]string, 0, len(v))
		for _, item := range v {
			parts = append(parts, fmt.Sprintf("%v", item))
		}
		strVal = strings.Join(parts, ";")
	case nil:
		return "<nil>"
	default:
		strVal = fmt.Sprintf("%v", v)
	}
	if maxLen > 3 && len(strVal) > maxLen {
		return strVal[:maxLen-3] + "..."
	}
	return strVal
}

func newStyledTable(columns []table.Column, rows []table.Row, height int) table.Model {
	t := table.New(
		table.WithColumns(columns),
		table.WithRows(rows),
		table.WithFocused(true),
		table.WithHeight(height),
	)

	s := table.DefaultStyles()
	s.Header = s.Header.
		BorderStyle(lipgloss.NormalBorder()).
		BorderForeground(lipgloss.Color("240")).
		Foreground(lipgloss.Color("39")).
		BorderBottom(true).
		Bold(true)
	s.Selected = s.Selected.
		Foreground(lipgloss.Color("229")).
		Background(lipgloss.Color("57")).
		Bold(false)
	t.SetStyles(s)
	return t
}

func writeCSV(w io.Writer, headers []string, rows [][]string) error {
	csvWriter := csv.NewWriter(w)
	if err := csvWriter.Write(headers); err != nil {
		return fmt.Errorf("writing csv header: %w", err)
	}
	for _, row := range rows {
		if err := csvWriter.Write(row); err != nil {
			return fmt.Errorf("writing csv record: %w", err)
		}
	}
	csvWriter.Flush()
	if err := csvWriter.Error(); err != nil {
		return fmt.Errorf("flushing csv writer: %w", err)
	}
	return nil
}
