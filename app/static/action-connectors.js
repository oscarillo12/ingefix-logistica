'use strict';

function downloadSkuLabel(product) {
  if (!product) return toast('Selecciona un producto para descargar su etiqueta', true);
  const barcode = Code128.svg(product.code);
  const width = barcode.match(/viewBox="0 0 ([0-9.]+) 65"/)?.[1];
  const inner = barcode.match(/<svg[^>]*>([\s\S]*)<\/svg>/)?.[1];
  if (!width || !inner) return toast('No se pudo generar el código de barras', true);
  const xml = value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="90mm" height="45mm" viewBox="0 0 900 450"><rect width="900" height="450" fill="white"/><text x="35" y="48" font-family="Arial" font-size="24" font-weight="700">INGEFIX · TEMUCO · BODEGA 08</text><text x="865" y="48" text-anchor="end" font-family="Arial" font-size="22">ABC ${xml(product.abc === 'ND' ? 'S/C' : product.abc)}</text><text x="35" y="105" font-family="Arial" font-size="27" font-weight="700">${xml(product.name)}</text><svg x="35" y="125" width="830" height="205" viewBox="0 0 ${width} 65" preserveAspectRatio="none">${inner}</svg><text x="450" y="370" text-anchor="middle" font-family="Arial" font-size="31" font-weight="700">${xml(product.code)}</text><text x="35" y="425" font-family="Arial" font-size="18">UBICACIÓN: ${xml(product.location || 'PENDIENTE DE ASIGNAR')}</text></svg>`;
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${String(product.code).replace(/[^a-zA-Z0-9_.-]/g, '_') || 'producto'}-etiqueta.svg`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('Etiqueta descargada. Ábrela e imprímela al 100 %.');
}

const warehousePageBeforeLabelDownload = warehousePage;
warehousePage = function () {
  let html = warehousePageBeforeLabelDownload().replace(
    '<button class="btn small" data-action="print-warehouse-label">Imprimir esta etiqueta</button>',
    `<div class="label-actions"><button class="btn small" data-action="download-label" data-code="${esc(warehouseSelected)}">Descargar etiqueta</button><button class="btn small" data-action="print-warehouse-label">Imprimir esta etiqueta</button></div>`
  );
  const marker = '<div class="warehouse-mini-steps">';
  const start = html.indexOf(marker);
  if (start >= 0) {
    const end = html.indexOf('</div>', start) + 6;
    const product = S?.products.find(item => item.code === warehouseSelected && item.recommended_count);
    const access = `<section class="warehouse-label-access"><div><strong>Etiquetas para pegar en los productos</strong><p>Descarga la etiqueta y luego escanéala aquí en WMS.</p></div>${product ? `<button class="btn small primary" data-action="download-label" data-code="${esc(product.code)}">Descargar etiqueta de la tarea</button>` : ''}<button class="btn small" data-action="open-labels">Buscar otro producto</button></section>`;
    html = html.slice(0, end) + access + html.slice(end);
  }
  return html;
};

const currentPositionBeforeCountGuidance = currentPosition;
currentPosition = function (product) {
  const html = currentPositionBeforeCountGuidance(product);
  const guidance = product.count_trigger == null
    ? '<div class="rop-count-guidance is-pending"><strong>Faltan datos para programar este conteo</strong><p>Confirma la demanda, el plazo y los días de revisión.</p></div>'
    : `<div class="rop-count-guidance ${product.count_alert ? 'is-due' : ''}"><strong>${product.wms_alert ? 'Ahora: contar antes de preparar la reposición' : product.count_alert ? 'Conteo preventivo recomendado' : 'Umbral para iniciar el conteo preventivo'}</strong><p>Verifica este SKU cuando su posición llegue a <b>${num(product.count_trigger)} unidades</b>: ROP más el consumo durante ${num(S.settings.review_days)} días de revisión. La prioridad ABC pone primero A y B. El conteo físico confirma el saldo antes de decidir si reponer.</p>${button('count', 'Contar este producto', 'small primary', productData(product))}</div>`;
  return html.replace('<p class="rop-snapshot-note">', guidance + '<p class="rop-snapshot-note">');
};

const foundProductBeforeLabelDownload = foundProduct;
foundProduct = function (code) {
  foundProductBeforeLabelDownload(code);
  const product = S?.products.find(item => item.code === String(code).trim());
  const result = document.querySelector('#scan-result');
  if (!product || !result || result.querySelector('[data-action="download-label"]')) return;
  const actions = result.querySelector('.scanned-product .actions, .warehouse-label-preview');
  if (actions) actions.insertAdjacentHTML('beforeend', `<button class="btn small" data-action="download-label" data-code="${esc(product.code)}">Descargar etiqueta</button>`);
};

const renderBeforeActionConnectors = render;
let previousManagerCountAlerts = null;
function renderRopNextStep() {
  const products = S?.products || [];
  const ready = products.filter(product => product.rop != null && product.position != null);
  const needsOrder = ready.filter(product => product.position <= product.rop).sort((a, b) => (a.position - a.rop) - (b.position - b.rop));
  const countTasks = products.filter(product => product.recommended_count && (product.count_alert || product.wms_alert)).sort((a, b) => (b.priority || 0) - (a.priority || 0));
  const incomplete = products.length - ready.length;
  const firstCount = countTasks[0];
  const firstOrder = needsOrder.find(product => product.suggested > 0 && !product.open_request);
  let message, action = '';
  if (!products.length) {
    message = 'Todavía no hay productos cargados para calcular reposición.';
    action = '<button class="btn small primary" data-go="integration">Cargar productos</button>';
  } else if (!ready.length) {
    message = 'Aún no se puede calcular el ROP. Faltan datos confirmados de demanda, plazo o colchón.';
    action = '<button class="btn small primary" data-go="integration">Completar datos</button>';
  } else if (firstCount) {
    message = `${firstCount.name} es el siguiente producto que debe verificarse físicamente. ${firstCount.wms_alert ? 'Ya llegó al punto de pedido.' : 'Se acerca al punto de pedido.'} A y B se priorizan por su movimiento.`;
    action = `<button class="btn small primary" data-action="count" data-code="${esc(firstCount.code)}">Contar este producto</button>`;
  } else if (firstOrder) {
    message = `${firstOrder.name} está bajo su punto de pedido y ya no tiene un conteo pendiente. El encargado puede preparar la solicitud.`;
    action = `<button class="btn small primary" data-action="request" data-code="${esc(firstOrder.code)}">Preparar borrador a Santiago</button>`;
  } else {
    message = `Hoy hay 0 productos bajo el punto de pedido. ${ready.length} productos tienen cálculo disponible.`;
  }
  if (needsOrder.length && !firstCount && !firstOrder) message += ` Hay ${needsOrder.length} producto(s) para revisar en el módulo de reposición.`;
  return `<section class="rop-next-step"><div class="rop-next-copy"><span>ROP · QUÉ HACER AHORA</span><h2>${firstCount ? 'Primero, confirma el inventario físico' : needsOrder.length ? 'Revisa la reposición' : ready.length ? 'No hay reposiciones urgentes' : 'Faltan datos para empezar'}</h2><p>${message}</p>${incomplete ? `<small>${incomplete} producto(s) sin datos suficientes; no generan alertas ROP.</small>` : ''}</div><div class="rop-next-actions">${action}${countTasks.length ? `<button class="btn small" data-go="counts">Ver conteos pendientes (${countTasks.length})</button>` : ''}</div></section>`;
}
render = function () {
  renderBeforeActionConnectors();
  if (page === 'replenish') {
    const pageTop = document.querySelector('#page .page-top');
    if (pageTop && !document.querySelector('#page .rop-next-step')) pageTop.insertAdjacentHTML('afterend', renderRopNextStep());
    document.querySelector('#page .workflow-lesson')?.remove();
    const grids = [...document.querySelectorAll('#page .rop-analysis-grid')];
    if (grids.length && !document.querySelector('#page .rop-technical-details')) {
      const details = document.createElement('details');
      details.className = 'rop-technical-details';
      details.innerHTML = '<summary>Ver cálculo, gráfico y datos de respaldo</summary>';
      grids[0].before(details);
      grids.forEach(grid => details.append(grid));
    }
  }
  if (!warehouseMode && page === 'overview') {
    const key = (S?.products || []).filter(product => product.recommended_count && product.count_alert).map(product => product.code).join('|');
    if (previousManagerCountAlerts !== null && key && key !== previousManagerCountAlerts) toast('Nuevos conteos preventivos para revisar antes del ROP.');
    previousManagerCountAlerts = key;
    const scanTool = [...document.querySelectorAll('.pro-tool')].find(card => card.textContent.includes('Conteo en bodega'));
    if (scanTool && !scanTool.querySelector('[data-action="open-labels"]')) scanTool.insertAdjacentHTML('beforeend', '<button class="pro-tool-guide" data-action="open-labels">Preparar e imprimir etiquetas →</button>');
  }
  if (page === 'labels' && !document.querySelector('[data-action="download-one-label"]')) {
    const selected = [...labelSelection];
    const preview = document.querySelector('.label-preview');
    if (preview && selected.length) {
      const product = S.products.find(item => item.code === selected[0]);
      if (product) preview.insertAdjacentHTML('beforeend', `<div class="label-download-action"><span>${selected.length === 1 ? 'Etiqueta seleccionada' : 'Descarga individual de la primera etiqueta seleccionada'}</span><button class="btn small primary" data-action="download-one-label" data-code="${esc(product.code)}">Descargar etiqueta SVG</button></div>`);
    }
  }
};

document.addEventListener('click', event => {
  const button = event.target.closest('[data-action="download-label"],[data-action="download-one-label"],[data-action="open-labels"],[data-action="wms-print-label"]');
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (button.dataset.action === 'open-labels') {
    if (!warehouseMode) { navigate('labels'); return; }
    const product = S.products.find(item => item.code === warehouseSelected) || S.products[0];
    const options = S.products.map(item => `<option value="${esc(item.code)}" ${item.code === product?.code ? 'selected' : ''}>${esc(item.code + ' · ' + item.name)}</option>`).join('');
    showModal('Etiquetas para la bodega', 'Elige el producto que vas a identificar con una etiqueta escaneable.', `<label for="wms-label-picker">Producto</label><select id="wms-label-picker">${options}</select><div id="wms-label-preview">${product ? `${labelMarkup(product)}<div class="label-actions"><button class="btn small primary" data-action="download-label" data-code="${esc(product.code)}">Descargar etiqueta</button><button class="btn small" data-action="wms-print-label" data-code="${esc(product.code)}">Imprimir etiqueta</button></div>` : 'No hay productos cargados.'}</div>`);
    return;
  }
  if (button.dataset.action === 'wms-print-label') { labelSelection = new Set([button.dataset.code]); printLabels(); return; }
  downloadSkuLabel(S?.products.find(item => item.code === button.dataset.code));
}, true);

document.addEventListener('change', event => {
  if (event.target.id !== 'wms-label-picker') return;
  const product = S?.products.find(item => item.code === event.target.value);
  if (!product) return;
  $('#wms-label-preview').innerHTML = `${labelMarkup(product)}<div class="label-actions"><button class="btn small primary" data-action="download-label" data-code="${esc(product.code)}">Descargar etiqueta</button><button class="btn small" data-action="wms-print-label" data-code="${esc(product.code)}">Imprimir etiqueta</button></div>`;
});

setInterval(() => {
  if (!warehouseMode && S && page === 'overview' && !document.querySelector('#modal[open]')) load();
}, 30000);
