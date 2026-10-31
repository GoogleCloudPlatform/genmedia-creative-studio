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
	"fmt"
	"time"

	"cloud.google.com/go/firestore"
	"github.com/charmbracelet/bubbles/table"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
)

type userDocsFetchedMsg struct {
	userEmail string
	table     table.Model
	err       error
}

type topUsersModel struct {
	table            table.Model
	viewport         viewport.Model
	showTable        bool
	header           string
	width, height    int
	col              *firestore.CollectionRef
	userDocs         table.Model
	showUserDocs     bool
	showUserDocPager bool
	err              error
}

func newTopUsersModel(t table.Model, col *firestore.CollectionRef) topUsersModel {
	return topUsersModel{
		table:     t,
		viewport:  viewport.New(120, 30),
		showTable: true,
		col:       col,
	}
}

func (m topUsersModel) Init() tea.Cmd { return nil }

func (m topUsersModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	case userDocsFetchedMsg:
		if msg.err != nil {
			m.err = msg.err
			return m, nil
		}
		m.header = fmt.Sprintf("User: %s", msg.userEmail)
		m.userDocs = msg.table
		m.showUserDocs = true
		m.showTable = false
		return m, nil
	case docFetchedMsg:
		if msg.err != nil {
			m.err = msg.err
			return m, nil
		}
		m.header = msg.header
		m.viewport.SetContent(msg.content)
		m.showUserDocs = false
		m.showUserDocPager = true
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
				selectedEmail := selectedRow[0]
				return m, fetchUserDocsCmd(m.col, selectedEmail)
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
			} else if m.showUserDocs {
				m.showUserDocs = false
				m.showTable = true
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

func (m topUsersModel) View() string {
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
		return fmt.Sprintf("Found %d users\n%s\n", len(m.table.Rows()), baseStyle.Render(m.table.View()))
	}
	return fmt.Sprintf("%s\n%s\n", AccentStyle.Render(m.header), baseStyle.Render(m.viewport.View()))
}

func fetchUserDocsCmd(col *firestore.CollectionRef, userEmail string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		docs, err := fetchDocsByUser(ctx, col, userEmail)
		if err != nil {
			return userDocsFetchedMsg{err: err}
		}

		columns := []table.Column{
			{Title: "ID", Width: 25},
			{Title: "MIME_TYPE", Width: 12},
			{Title: "USER_EMAIL", Width: 25},
			{Title: "TIMESTAMP", Width: 20},
			{Title: "MODEL", Width: 20},
		}
		rows := make([]table.Row, len(docs))
		for i, doc := range docs {
			var tsStr string
			if ts := timeField(doc, "timestamp"); !ts.IsZero() {
				tsStr = ts.Format(timestampLayout)
			}
			rows[i] = table.Row{
				stringField(doc, "id"),
				stringField(doc, "mime_type"),
				stringField(doc, "user_email"),
				tsStr,
				stringField(doc, "model"),
			}
		}
		t := newStyledTable(columns, rows, 15)
		return userDocsFetchedMsg{
			userEmail: userEmail,
			table:     t,
		}
	}
}
