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
  return warehousePageBeforeLabelDownload().replace(
    '<button class="btn small" data-action="print-warehouse-label">Imprimir esta etiqueta</button>',
    `<div class="label-actions"><button class="btn small" data-action="download-label" data-code="${esc(warehouseSelected)}">Descargar etiqueta</button><button class="btn small" data-action="print-warehouse-label">Imprimir esta etiqueta</button></div>`
  );
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
render = function () {
  renderBeforeActionConnectors();
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
  const button = event.target.closest('[data-action="download-label"],[data-action="download-one-label"],[data-action="open-labels"]');
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (button.dataset.action === 'open-labels') { navigate('labels'); return; }
  downloadSkuLabel(S?.products.find(item => item.code === button.dataset.code));
}, true);

setInterval(() => {
  if (!warehouseMode && S && page === 'overview' && !document.querySelector('#modal[open]')) load();
}, 30000);
