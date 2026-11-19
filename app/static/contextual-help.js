'use strict';

// Small contextual guides replace the upfront eight-step tour.
let guideContextShown = null;
let guideDismissed = false;
let penguinAlertSignature = null;

function guideForCurrentTool() {
  const ctx = warehouseMode ? 'warehouse' : page;
  const entries = {
    overview: ['Inicio', 'Mira primero las alertas. ABC prioriza productos; el conteo confirma lo que hay; ROP avisa cu\u00e1ndo revisar una reposici\u00f3n.', 'abc', 'Ver prioridades ABC'],
    abc: ['Clasificador ABC', 'A y B concentran m\u00e1s salidas en los documentos cargados. \u00dasalos para decidir qu\u00e9 productos revisar con mayor frecuencia.', 'counts', 'Ver conteos prioritarios'],
    counts: ['Conteo c\u00edclico', 'Esta cola muestra productos A/B vencidos, cerca del ROP o ligados a pedidos pr\u00f3ximos. Escanea y anota lo que encuentres; el encargado ver\u00e1 si debe preparar un pedido.', 'replenish', 'Ver reposici\u00f3n'],
    forecast: ['Demanda', 'El historial por producto estima consumo. Sirve para orientar el punto de pedido; el plazo de Santiago y el colch\u00f3n deben confirmarse con la empresa.', 'replenish', 'Volver al ROP'],
    integration: ['Datos y Softland', 'Aqu\u00ed se cargan archivos o se prepara el conector. El ROP necesita demanda v\u00e1lida, plazo y colch\u00f3n confirmados; sin esos valores no inventa un umbral.', 'replenish', 'Volver al ROP'],
    labels: ['Etiquetas WMS', 'Elige el producto y descarga o imprime su etiqueta con c\u00f3digo de barras para identificarlo en bodega.', 'scan', 'Ir al esc\u00e1ner'],
    scan: ['WMS - bodega', 'Solo necesitas elegir la tarea prioritaria, escanear la etiqueta y guardar la cantidad f\u00edsica. El motivo indica por qu\u00e9 se eligi\u00f3 el producto.', 'labels', 'Preparar etiqueta'],
    commitments: ['Pedidos pr\u00f3ximos', 'Los productos comprometidos se verifican antes del picking. Una diferencia f\u00edsica permite avisar al encargado antes de prometer el despacho.', 'counts', 'Confirmar inventario'],
    receipts: ['Recepciones', 'Registra lo que realmente lleg\u00f3, incluso si es parcial, y luego conc\u00edlialo con Softland. Una recepci\u00f3n observada no modifica el saldo ERP.', 'integration', 'Ver integraci\u00f3n'],
    credits: ['Notas de cr\u00e9dito', 'Una nota comercial no significa que el producto volvi\u00f3. Cuenta las devoluciones y concilia el ingreso f\u00edsico antes de considerar stock.', 'receipts', 'Ver recepciones'],
    research: ['Mejoras log\u00edsticas', 'Revisa propuestas tecnol\u00f3gicas aplicables y sus fuentes antes de incorporarlas al piloto.', 'integration', 'Ver integraci\u00f3n'],
    audit: ['Trazabilidad', 'Consulta qui\u00e9n registr\u00f3 un conteo o evento y cu\u00e1ndo. La bit\u00e1cora ayuda a investigar diferencias.', 'counts', 'Ver conteos']
  };
  const entry = entries[ctx];
  if (!entry) return null;
  let [title, message, target, cta] = entry;
  if (ctx === 'replenish') {
    const products = S?.products || [];
    const ready = products.filter(p => p.rop != null).length;
    const history = products.filter(p => p.forecast?.last_day || p.daily != null).length;
    message = ready
      ? `El ROP compara el consumo durante el plazo con el colch\u00f3n. Hay ${ready} productos calculables; confirma la posici\u00f3n f\u00edsica antes de preparar una solicitud.`
      : `Hay historial de salidas para ${history} producto(s), pero el plazo Santiago-Temuco y el colch\u00f3n no est\u00e1n confirmados. Por eso el ROP queda pendiente, no en cero. Completa esos datos en Integraci\u00f3n > Par\u00e1metros del piloto.`;
    target = ready ? 'counts' : 'integration';
    cta = ready ? 'Ver conteos' : 'Completar par\u00e1metros';
  }
  return { ctx, title, message, target, cta, warehouse: ctx === 'warehouse' };
}

function renderContextGuide() {
  const pageEl = document.querySelector('#page');
  if (!pageEl || !S) return;
  const guide = guideForCurrentTool();
  if (!guide) return;
  if (guide.ctx !== guideContextShown) {
    guideContextShown = guide.ctx;
    guideDismissed = false;
  }
  if (guideDismissed || pageEl.querySelector('.context-guide-card')) return;
  const next = guide.warehouse
    ? `<button class="btn small primary" data-action="open-labels">${esc(guide.cta)}</button>`
    : `<button class="btn small primary" data-go="${esc(guide.target)}">${esc(guide.cta)}</button>`;
  const card = `<aside class="context-guide-card" aria-label="Ayuda de ${esc(guide.title)}"><div class="context-guide-copy"><span class="context-guide-kicker">AYUDA RAPIDA</span><strong>${esc(guide.title)}</strong><p>${esc(guide.message)}</p><div class="context-guide-actions">${next}<button class="context-guide-close" data-action="guide-close" aria-label="Cerrar ayuda">Entendido</button></div></div></aside>`;
  const anchor = pageEl.querySelector('.page-top, .warehouse-header');
  if (anchor) anchor.insertAdjacentHTML('afterend', card);
  else pageEl.insertAdjacentHTML('afterbegin', card);
}

function penguinArt() {
  return '<svg class="penguin-alert-avatar" viewBox="0 0 72 72" role="img" aria-label="Pingüino ayudante"><ellipse cx="36" cy="66" rx="22" ry="4" fill="#dce6df"/><g class="penguin-alert-body"><path d="M36 7C19 7 12 23 14 43c2 16 10 23 22 23s20-7 22-23C60 23 53 7 36 7Z" fill="#263b3a"/><ellipse cx="36" cy="42" rx="14" ry="19" fill="#fff"/><ellipse cx="30" cy="29" rx="2.5" ry="3.2" fill="#172b29"/><ellipse cx="42" cy="29" rx="2.5" ry="3.2" fill="#172b29"/><path d="m32 35 4 4 4-4Z" fill="#f4ad42"/><path d="M17 59q-6 3-10 0m38 0q6 3 10 0" fill="none" stroke="#f4ad42" stroke-width="4" stroke-linecap="round"/></g></svg>';
}

function renderPenguinAlert() {
  if (!S || !document.body) return;
  const countTasks = S.products.filter(p => p.recommended_count && (['A', 'B'].includes(p.abc) || p.count_alert || p.wms_alert || p.upcoming_orders));
  countTasks.sort((a, b) => (b.priority || 0) - (a.priority || 0));
  const first = countTasks[0];
  const orderAlerts = S.products.filter(p => p.wms_alert && p.rop != null && p.position != null).sort((a, b) => (a.position - a.rop) - (b.position - b.rop));
  const order = orderAlerts[0];
  const warehouse = warehouseMode || S.session_role === 'warehouse';
  let title, message, action = '', target = 'counts', productCode = '';
  if (first) {
    const reason = first.wms_alert ? 'ya alcanz\u00f3 el ROP' : first.count_alert ? 'se acerca al colch\u00f3n del ROP' : first.upcoming_orders ? 'est\u00e1 ligado a un pedido pr\u00f3ximo' : `tiene conteo preventivo por rotaci\u00f3n clase ${first.abc}`;
    title = 'Aviso de conteo';
    message = `${first.name} ${reason}. Confirma la cantidad f\u00edsica antes de que el encargado decida reponer.`;
    action = warehouse ? 'Ir a escanear' : 'Ver productos para contar';
    target = warehouse ? 'warehouse' : 'counts';
    productCode = first.code;
  } else if (order && !warehouse) {
    title = 'Aviso para el encargado';
    message = `${order.name} est\u00e1 en o bajo su ROP y no tiene un conteo pendiente. Revisa la reposici\u00f3n a Santiago.`;
    action = 'Revisar reposici\u00f3n';
    target = 'replenish';
    productCode = order.code;
  } else {
    title = 'Estoy atento a la bodega';
    const hasRop = S.products.some(p => p.rop != null);
    message = hasRop
      ? 'Te avisar\u00e9 cuando un producto A/B venza su conteo, se acerque al colch\u00f3n del ROP o tenga un pedido pr\u00f3ximo.'
      : 'Te avisar\u00e9 qu\u00e9 producto contar. El aviso por ROP comenzar\u00e1 cuando el encargado confirme plazo y colch\u00f3n.';
    action = warehouse ? 'Ver tareas de bodega' : 'Ver conteos';
    target = warehouse ? 'warehouse' : 'counts';
  }
  const signature = `${target}|${productCode}|${title}`;
  const node = document.getElementById('penguin-alert');
  const button = warehouse && productCode
    ? `<button class="penguin-alert-action" data-action="penguin-open-task" data-code="${esc(productCode)}">${esc(action)}</button>`
    : `<button class="penguin-alert-action" data-action="penguin-open" data-target="${esc(target)}" ${productCode ? `data-code="${esc(productCode)}"` : ''}>${esc(action)}</button>`;
  const content = `<div class="penguin-alert-inner"><div class="penguin-alert-character">${penguinArt()}<span class="penguin-alert-dot" aria-hidden="true"></span></div><div class="penguin-alert-copy"><span class="penguin-alert-kicker">AYUDANTE DE BODEGA</span><strong>${esc(title)}</strong><p>${esc(message)}</p>${button}</div></div>`;
  if (node) node.innerHTML = content;
  else document.body.insertAdjacentHTML('beforeend', `<aside id="penguin-alert" class="penguin-alert" role="status" aria-live="polite">${content}</aside>`);
  if (penguinAlertSignature !== null && signature !== penguinAlertSignature && first && !warehouse) toast(`El pingüino tiene un aviso de conteo: ${first.name}.`);
  penguinAlertSignature = signature;
}

const renderBeforeContextGuide = render;
render = function () {
  renderBeforeContextGuide();
  document.querySelectorAll('#page [href^="/api/"], #page [src^="/api/"]').forEach(node => {
    const attribute = node.hasAttribute('href') ? 'href' : 'src';
    node.setAttribute(attribute, apiUrl(node.getAttribute(attribute)));
  });
  const policyForm = document.querySelector('#settings-form');
  if (policyForm && !policyForm.elements.planning_confirmed) {
    policyForm.querySelector('.form-grid')?.insertAdjacentHTML('beforeend', `<label class="check-label wide"><input name="planning_confirmed" type="checkbox" ${S.settings.planning_confirmed ? 'checked' : ''}>Confirmo que el plazo y el colch\u00f3n ingresados fueron validados con bodega/abastecimiento para esta demostraci\u00f3n.</label>`);
  }
  renderContextGuide();
  renderPenguinAlert();
};

function openTour() {
  guideDismissed = false;
  renderContextGuide();
  document.querySelector('.context-guide-card')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function contextHelp() { openTour(); }

document.addEventListener('click', event => {
  const control = event.target.closest('[data-action]');
  if (!control) return;
  if (['context-help', 'warehouse-help', 'start-tour'].includes(control.dataset.action)) {
    event.preventDefault();
    event.stopImmediatePropagation();
    openTour();
    return;
  }
  if (control.dataset.action === 'guide-close') {
    event.preventDefault();
    event.stopImmediatePropagation();
    guideDismissed = true;
    control.closest('.context-guide-card')?.remove();
    return;
  }
  if (control.dataset.action === 'penguin-open') {
    event.preventDefault();
    event.stopImmediatePropagation();
    navigate(control.dataset.target || 'counts');
    return;
  }
  if (control.dataset.action === 'penguin-open-task') {
    event.preventDefault();
    event.stopImmediatePropagation();
    warehouseSelected = control.dataset.code;
    render();
    document.querySelector('.warehouse-camera-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    document.querySelector('#scan-code')?.focus({ preventScroll: true });
  }
}, true);
