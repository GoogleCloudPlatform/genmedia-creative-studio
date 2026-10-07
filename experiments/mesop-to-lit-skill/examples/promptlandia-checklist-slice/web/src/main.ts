// App entry. Registers the STABLE Material Web components the shell uses, applies
// the M3 theme (system default + persisted override), and loads the shell +
// pages. Custom components self-register via their @customElement decorators.

import '@material/web/icon/icon.js';
import '@material/web/iconbutton/icon-button.js';
import '@material/web/list/list.js';
import '@material/web/list/list-item.js';

import { applyTheme } from './theme';
import './app-root';
import './pages/page-checklist';
import './pages/page-stub';

applyTheme();
