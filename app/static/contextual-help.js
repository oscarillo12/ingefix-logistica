'use strict';

// Ayuda breve al entrar a cada herramienta; reemplaza la visita guiada de ocho pasos.
let guideContextShown = null;
let guideDismissed = false;

function guideForCurrentTool() {
  const ctx = warehouseMode ? 'warehouse' : page;
  const entries = {
    overview: ['Inicio', 'Mira primero las alertas. ABC prioriza productos; el conteo confirma lo que hay; ROP avisa cuándo revisar una reposición.', 'abc', 'Ver prioridades ABC →'],
    abc: ['Clasificador ABC', 'A y B concentran más salidas en los documentos cargados. Úsalos para decidir qué productos revisar con mayor frecuencia.', 'counts', 'Ver conteos prioritarios →'],
    counts: ['Conteo cíclico', 'Esta cola muestra productos A/B vencidos, cerca del ROP o ligados a pedidos próximos. Escanea y anota lo que encuentres; el encargado verá si debe preparar un pedido.', 'replenish', 'Ver reposición →'],
    forecast: ['Demanda', 'El historial por producto estima consumo. Sirve para orientar el punto de pedido; el plazo de Santiago y el colchón deben confirmarse con la empresa.', 'replenish', 'Volver al ROP →'],
    integration: ['Datos y Softland', 'Aquí se cargan archivos o se prepara el conector. El ROP necesita demanda válida, plazo y colchón confirmados; sin esos valores no inventa un umbral.', 'replenish', 'Volver al ROP →'],
    labels: ['Etiquetas WMS', 'Elige el producto y descarga o imprime su etiqueta con código de barras para identificarlo en bodega.', 'scan', 'Ir al escáner →'],
    scan: ['WMS · bodega', 'Solo necesitas elegir la tarea prioritaria, escanear la etiqueta y guardar la cantidad física. El motivo indica por qué se eligió el producto.', 'labels', 'Preparar etiqueta →'],
    commitments: ['Pedidos próximos', 'Los productos comprometidos se verifican antes del picking. Una diferencia física permite avisar al encargado antes de prometer el despacho.', 'counts', 'Confirmar inventario →'],
    receipts: ['Recepciones', 'Registra lo que realmente llegó, incluso si es parcial, y luego concílialo con Softland. Una recepción observada no modifica el saldo ERP.', 'integration', 'Ver integración →'],
    credits: ['Notas de crédito', 'Una nota comercial no significa que el producto volvió. Cuenta las devoluciones y concilia el ingreso físico antes de considerar stock.', 'receipts', 'Ver recepciones →'],
    research: ['Mejoras logísticas', 'Revisa propuestas tecnológicas aplicables y sus fuentes antes de incorporarlas al piloto.', 'integration', 'Ver integración →'],
    audit: ['Trazabilidad', 'Consulta quién registró un conteo o evento y cuándo. La bitácora ayuda a investigar diferencias.', 'counts', 'Ver conteos →']
  };
  const entry = entries[ctx];
  if (!entry) return null;
  let [title, message, target, cta] = entry;
  if (ctx === 'replenish') {
    const products = S?.products || [];
    const ready = products.filter(p => p.rop != null).length;
    const history = products.filter(p => p.forecast?.last_day || p.daily != null).length;
    message = ready
      ? `El ROP compara el consumo durante el plazo con el colchón. Hay ${ready} productos calculables; confirma la posición física antes de preparar una solicitud.`
      : `Hay ${history} productos con salidas o historial para estimar demanda, pero el plazo Santiago–Temuco y el colchón no están confirmados. Por eso no aparece un ROP numérico; ingrésalos en Integración → Parámetros del piloto.`;
    target = ready ? 'counts' : 'integration';
    cta = ready ? 'Ver conteos →' : 'Completar parámetros →';
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
  const card = `<aside class="context-guide-card" aria-label="Ayuda de ${esc(guide.title)}"><div class="context-guide-copy"><span class="context-guide-kicker">AYUDA RÁPIDA</span><strong>${esc(guide.title)}</strong><p>${esc(guide.message)}</p><div class="context-guide-actions">${next}<button class="context-guide-close" data-action="guide-close" aria-label="Cerrar ayuda">Entendido ×</button></div></div><div class="context-guide-mascot">${penguinGuide('Te indico solo el paso de esta pantalla.')}</div></aside>`;
  const anchor = pageEl.querySelector('.page-top, .warehouse-header');
  if (anchor) anchor.insertAdjacentHTML('afterend', card);
  else pageEl.insertAdjacentHTML('afterbegin', card);
}

const renderBeforeContextGuide = render;
render = function () {
  renderBeforeContextGuide();
  const policyForm = document.querySelector('#settings-form');
  if (policyForm && !policyForm.elements.planning_confirmed) {
    policyForm.querySelector('.form-grid')?.insertAdjacentHTML('beforeend', `<label class="check-label wide"><input name="planning_confirmed" type="checkbox" ${S.settings.planning_confirmed ? 'checked' : ''}>Confirmo que el plazo y el colchón ingresados fueron validados con bodega/abastecimiento para esta demostración.</label>`);
  }
  renderContextGuide();
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
  }
}, true);
