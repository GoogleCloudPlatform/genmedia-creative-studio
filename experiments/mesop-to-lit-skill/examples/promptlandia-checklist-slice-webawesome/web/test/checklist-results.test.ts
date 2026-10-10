import { describe, it, expect } from 'vitest';
import { fixture, html } from '@open-wc/testing-helpers';
import '../src/components/checklist-results';
import type { ChecklistResults } from '../src/components/checklist-results';
import type { ChecklistResponse } from '../src/api/types';

const issueAndNoIssue: ChecklistResponse = {
  categories: [
    {
      name: 'clarity',
      has_issue: true,
      explanation:
        '**Impact Analysis:**\nMay confuse the model.\n\n**Suggested Solution:**\nBe explicit.',
      items: [
        {
          issue_name: 'ambiguous_instruction',
          location_in_prompt: 'the opening line',
          rationale: "The phrase 'do the thing' is vague.",
          impact_analysis: '',
          severity: '',
          solution: '',
        },
      ],
    },
    {
      name: 'typos',
      has_issue: false,
      explanation: 'No issues found.',
      items: [],
    },
  ],
  raw: null,
};

async function mount(data: ChecklistResponse): Promise<ChecklistResults> {
  const el = await fixture<ChecklistResults>(
    html`<checklist-results .data=${data}></checklist-results>`,
  );
  await el.updateComplete;
  return el;
}

describe('checklist-results', () => {
  it('renders the issue section with a humanized category and item', async () => {
    const el = await mount(issueAndNoIssue);
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('Checklist found 1 issue');
    expect(text).toContain('Clarity'); // humanized from "clarity"
    expect(text).toContain('Ambiguous Instruction'); // humanized issue_name
    // flag icon present for the issue category
    const icons = Array.from(
      el.shadowRoot!.querySelectorAll('.material-symbols-outlined'),
    ).map((n) => n.textContent?.trim());
    expect(icons).toContain('flag');
  });

  it('renders the no-issue section with a passing check', async () => {
    const el = await mount(issueAndNoIssue);
    const text = el.shadowRoot!.textContent ?? '';
    expect(text).toContain('The following checks passed without issues');
    expect(text).toContain('Typos');
    const icons = Array.from(
      el.shadowRoot!.querySelectorAll('.material-symbols-outlined'),
    ).map((n) => n.textContent?.trim());
    expect(icons).toContain('check_circle');
  });

  it('pluralizes correctly for multiple issues', async () => {
    const two: ChecklistResponse = {
      categories: [
        { ...issueAndNoIssue.categories[0], name: 'a' },
        { ...issueAndNoIssue.categories[0], name: 'b' },
      ],
      raw: null,
    };
    const el = await mount(two);
    expect(el.shadowRoot!.textContent).toContain('Checklist found 2 issues');
  });

  it('renders the parse-fallback raw text when there are no categories', async () => {
    const el = await mount({ categories: [], raw: 'totally unparseable output' });
    const md = el.shadowRoot!.querySelector('md-markdown');
    expect(md).toBeTruthy();
    await (md as any).updateComplete;
    expect(md!.shadowRoot!.textContent).toContain('totally unparseable output');
  });
});
