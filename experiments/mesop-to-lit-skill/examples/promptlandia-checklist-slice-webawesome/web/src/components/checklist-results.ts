// checklist-results: the bespoke domain component (Q5 custom, no M3 equivalent;
// component-decision-framework #13). Renders a ChecklistResponse as an
// issue/no-issue card grid with flag/check icons, nested per-item detail,
// dividers, and per-category explanation -- equivalent to Mesop's
// render_pydantic_response. One component serves /checklist and /video-checklist.

import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import type { ChecklistCategory, ChecklistResponse } from '../api/types';
import './md-markdown';

function humanize(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

@customElement('checklist-results')
export class ChecklistResults extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
    .section-title {
      font-weight: 700;
      font-size: 18px;
      margin: 0 0 12px 0;
      color: var(--md-sys-color-on-background, #191c20);
    }
    .grid {
      display: flex;
      flex-direction: row;
      flex-wrap: wrap;
      gap: 16px;
    }
    .category {
      flex-grow: 1;
      flex-basis: 350px;
      min-width: 300px;
      display: flex;
      flex-direction: column;
    }
    .category-name {
      font-weight: 700;
      font-size: 16px;
      margin-bottom: 8px;
    }
    .card {
      background: var(--md-sys-color-surface-container-lowest, #fff);
      border: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
      border-radius: 12px;
      padding: 16px;
      height: 100%;
    }
    .item-head {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .item-name {
      font-weight: 500;
    }
    .detail {
      font-size: 13px;
      margin: 0 0 8px 32px;
    }
    .divider {
      border: none;
      border-top: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
      margin: 8px 0;
    }
    .explanation-label {
      font-weight: 700;
      font-size: 13px;
      margin: 8px 0 4px 0;
    }
    .passed {
      background: var(--md-sys-color-surface-container-lowest, #fff);
      border: 1px solid var(--md-sys-color-outline-variant, #c4c6d0);
      border-radius: 12px;
      padding: 16px;
    }
    .passed-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .flag {
      color: var(--md-sys-color-error, #ba1a1a);
    }
    .check {
      color: var(--md-sys-color-success, #146c2e);
    }
    .fallback {
      background: var(--md-sys-color-surface-container, #eef0f5);
      border-radius: 12px;
      padding: 16px;
    }
    .block {
      margin-top: 24px;
    }
  `;

  @property({ attribute: false }) data: ChecklistResponse | null = null;

  private renderItem(item: {
    issue_name: string;
    location_in_prompt: string;
    rationale: string;
  }, isLast: boolean) {
    const detailMd = [
      item.location_in_prompt
        ? `**Location:** ${item.location_in_prompt}`
        : '',
      item.rationale ? `${item.rationale}` : '',
    ]
      .filter(Boolean)
      .join('\n\n');
    return html`
      <div class="item">
        <div>
          <div class="item-head">
            <span class="material-symbols-outlined flag">flag</span>
            <span class="item-name">${humanize(item.issue_name)}</span>
          </div>
          ${detailMd
            ? html`<md-markdown class="detail" .text=${detailMd}></md-markdown>`
            : nothing}
        </div>
        ${isLast ? nothing : html`<hr class="divider" />`}
      </div>
    `;
  }

  private renderIssueCategory(cat: ChecklistCategory) {
    return html`
      <div class="category">
        <div class="category-name">${humanize(cat.name)}</div>
        <div class="card">
          ${cat.items.map((it, i) =>
            this.renderItem(it, i === cat.items.length - 1),
          )}
          ${cat.explanation
            ? html`
                <div class="explanation">
                  ${cat.items.length
                    ? html`<hr class="divider" />`
                    : nothing}
                  <div class="explanation-label">Category Explanation:</div>
                  <md-markdown .text=${cat.explanation}></md-markdown>
                </div>
              `
            : nothing}
        </div>
      </div>
    `;
  }

  render() {
    const data = this.data;
    if (!data) return nothing;

    // Parse-fallback path: no structured categories but raw text present.
    if (data.categories.length === 0 && data.raw) {
      return html`
        <div class="fallback">
          <md-markdown .text=${'```\n' + data.raw + '\n```'}></md-markdown>
        </div>
      `;
    }

    const withIssues = data.categories.filter((c) => c.has_issue);
    const withoutIssues = data.categories.filter((c) => !c.has_issue);
    // Build the heading as a single string so the rendered text is cleanly
    // single-spaced ("Checklist found 1 issue"); interpolating the count and the
    // pluralized word as separate template expressions injects the template's
    // own newline/indentation between them.
    const issueHeading = `Checklist found ${withIssues.length} ${
      withIssues.length === 1 ? 'issue' : 'issues'
    }`;

    // NOTE: the output is wrapped in a container <div> on purpose. A nested
    // TemplateResult placed directly at a template's root (no enclosing element)
    // is mis-parsed by happy-dom in the test env, committing as literal "<?>"
    // text instead of the template. Keeping a static wrapper element around all
    // dynamic child parts avoids that quirk (and costs nothing in the browser).
    return html`
      <div class="results">
        ${withIssues.length
          ? html`
              <h2 class="section-title">${issueHeading}</h2>
              <div class="grid">
                ${withIssues.map((c) => this.renderIssueCategory(c))}
              </div>
            `
          : nothing}
        ${withoutIssues.length
          ? html`
              <div class="block">
                <h2 class="section-title">
                  The following checks passed without issues
                </h2>
                <div class="passed">
                  ${withoutIssues.map(
                    (c) => html`
                      <div class="passed-row">
                        <span class="material-symbols-outlined check">check_circle</span>
                        <span class="item-name">${humanize(c.name)}</span>
                      </div>
                    `,
                  )}
                </div>
              </div>
            `
          : nothing}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'checklist-results': ChecklistResults;
  }
}
