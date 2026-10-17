// App entry. Registers the Web Awesome components the shell uses, applies
// the theme (system default + persisted override), and loads the shell +
// pages. Custom components self-register via their @customElement decorators.

import '@awesome.me/webawesome/dist/styles/themes/default.css';
import '@awesome.me/webawesome/dist/components/button/button.js';
import '@awesome.me/webawesome/dist/components/details/details.js';
import '@awesome.me/webawesome/dist/components/drawer/drawer.js';
import '@awesome.me/webawesome/dist/components/icon/icon.js';

import { applyTheme } from './theme';
import './app-root';
import './pages/page-checklist';
import './pages/page-stub';

applyTheme();
