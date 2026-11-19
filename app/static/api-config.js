'use strict';
// The static Render frontend talks to the existing Render API. Local runs remain same-origin.
window.INGEFIX_API_BASE = location.hostname === 'ingefix-control-logistico-ui.onrender.com'
  ? 'https://ingefix-control-logistico.onrender.com'
  : '';
