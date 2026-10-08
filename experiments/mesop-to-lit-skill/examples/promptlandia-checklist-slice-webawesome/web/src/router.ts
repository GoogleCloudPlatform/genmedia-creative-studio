// Client router (target-architecture §4.2). The single index-keyed me.navigate
// becomes a declarative @vaadin/router route table. FastAPI serves the SPA and
// deep links fall through to index.html (§7.1).

import { Router } from '@vaadin/router';

export interface NavItem {
  path: string;
  label: string;
  icon: string;
}

// Nav-visible routes (order = sidenav order). /playground stays routed-but-hidden.
export const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Improver', icon: 'auto_fix_high' },
  { path: '/prompt', label: 'Generate', icon: 'edit_note' },
  { path: '/checklist', label: 'Checklist', icon: 'fact_check' },
  { path: '/video-checklist', label: 'Video Checklist', icon: 'videocam' },
  { path: '/trimmer', label: 'Trimmer', icon: 'content_cut' },
  { path: '/settings', label: 'Settings', icon: 'settings' },
];

export function initRouter(outlet: HTMLElement): Router {
  const router = new Router(outlet);
  router.setRoutes([
    { path: '/', component: 'page-stub' },
    { path: '/prompt', component: 'page-stub' },
    { path: '/checklist', component: 'page-checklist' },
    { path: '/video-checklist', component: 'page-stub' },
    { path: '/trimmer', component: 'page-stub' },
    { path: '/settings', component: 'page-stub' },
    { path: '/playground', component: 'page-stub' },
    { path: '(.*)', component: 'page-checklist' },
  ]);
  return router;
}
