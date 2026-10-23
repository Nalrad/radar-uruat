// ── UI: sidebar, cards, filtros, toasts e indicadores ───────
window.UI = (function () {
  let embarcacoes = [];
  let activeFilter = 'todos';
  let selectedId = null;
  const etaCache = {};      // id -> info do ETA (preenchida de forma assíncrona)
  const gradeCache = {};    // destino -> rota da grade pública (partidas/tarifas)
  const ultimaAtualizacao = {}; // id -> timestamp ms do último sinal recebido

  // Padrão náutico: mostrar nós E km/h (docs §5.2)
  function velocidadeFormatada(no) {
    if (!Number.isFinite(no)) return '—';
    return `${no.toFixed(1)} nós (${(no * 1.852).toFixed(1)} km/h)`;
  }

  // "atualizado há Xs" — qualidade percebida do dado (docs §5.3)
  function idadeDoSinal(e) {
    const t = ultimaAtualizacao[e.id];
    if (!t) return 'agora';
    const seg = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (seg < 60) return `atualizado há ${seg}s`;
    const min = Math.round(seg / 60);
    return `atualizado há ${min} min`;
  }

  function sinalEnvelhecido(e) {
    const t = ultimaAtualizacao[e.id];
    return !!t && (Date.now() - t) / 1000 > CONFIG.STALE_AFTER_SEC;
  }

  function marcarRecebido(id) { ultimaAtualizacao[id] = Date.now(); }

  // Preço em centavos -> "R$ 120,00" (dinheiro nunca é float na origem — docs §4)
  function precoFormatado(centavos) {
    if (!Number.isFinite(centavos)) return '—';
    return 'R$ ' + (centavos / 100).toFixed(2).replace('.', ',');
  }

  // Linha comercial do card: "Óbidos · sáb 05:30 · a partir de R$ 80,00"
  function linhaGrade(e) {
    const rota = gradeCache[e.destino] || Object.values(gradeCache)[0];
    if (!rota || !rota.partidas || !rota.partidas.length) return '';
    const p = rota.partidas[0];            // partidas já vêm ordenadas por dia/hora
    const maisBarata = Math.min(...rota.tarifas.map(t => t.preco_centavos));
    const txt = `${rota.destino} · ${p.dia_nome} ${p.hora}`;
    return rota.tarifas.length ? `${txt} · a partir de ${precoFormatado(maisBarata)}` : txt;
  }

  // ── CARD HTML ──────────────────────────────────────────────
  function tipoClass(tipo) { return (tipo || '').toLowerCase(); }

  function makeCard(e) {
    const sel = selectedId === e.id;
    const eta = etaCache[e.id];
    const etaTxt = eta && eta.eta_tempo_min != null
      ? `ETA ~${Math.round(eta.eta_tempo_min)} min`
      : '';
    const gradeTxt = linhaGrade(e);
    return `
      <div class="vessel-card ${tipoClass(e.tipo)} ${sel ? 'selected' : ''}"
           id="card-${e.id}" role="button" tabindex="0"
           aria-label="Embarcação ${e.nome}, ${e.tipo}"
           data-id="${e.id}">
        <div class="vc-header">
          <span class="vc-icon">${e.tipo === 'Turismo' ? '⛵' : e.tipo === 'Pesca' ? '🎣' : e.tipo === 'Carga' ? '🛳️' : '🚢'}</span>
          <span class="vc-name">${e.nome}</span>
          <span class="vc-tipo">${e.tipo}</span>
        </div>
        <div class="vc-data">
          <div class="vc-item">Veloc. <span>${velocidadeFormatada(e.velocidade)}</span></div>
          <div class="vc-item">${etaTxt || 'Bandeira <span>' + e.bandeira + '</span>'}</div>
        </div>
        ${gradeTxt ? `<div class="vc-grade">${gradeTxt}</div>` : ''}
        <div class="vc-coords">${e.latitude.toFixed(5)}, ${e.longitude.toFixed(5)} · ${idadeDoSinal(e)}</div>
      </div>`;
  }

  // ── RENDER SIDEBAR ─────────────────────────────────────────
  function renderSidebar() {
    const filtered = activeFilter === 'todos'
      ? embarcacoes
      : embarcacoes.filter(e => e.tipo === activeFilter);

    document.getElementById('vessel-list').innerHTML = filtered.length
      ? filtered.map(makeCard).join('')
      : `<p class="empty-state">Nenhuma embarcação nesta categoria.</p>`;

    document.getElementById('total-count').textContent = embarcacoes.length;
  }

  // Delegação de eventos: cards são recriados a cada poll; um único
  // listener na lista evita vazamento de handlers inline (onclick=...).
  function bindListClicks(onSelect) {
    document.getElementById('vessel-list').addEventListener('click', ev => {
      const card = ev.target.closest('.vessel-card');
      if (card) onSelect(Number(card.dataset.id));
    });
    document.getElementById('vessel-list').addEventListener('keydown', ev => {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      const card = ev.target.closest('.vessel-card');
      if (card) { ev.preventDefault(); onSelect(Number(card.dataset.id)); }
    });
  }

  // ── SELECT VESSEL ──────────────────────────────────────────
  function selectVessel(id, embarcacao) {
    selectedId = id;
    if (embarcacao) MAPA.focarEmbarcacao(embarcacao);
    renderSidebar();
    if (window.innerWidth <= 768) fecharSidebarMobile();
  }

  function fecharSidebarMobile() {
    const sb = document.getElementById('sidebar');
    sb.classList.remove('open');
    document.getElementById('menu-btn').setAttribute('aria-expanded', 'false');
  }

  // ── FILTROS ────────────────────────────────────────────────
  function bindFilters() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        renderSidebar();
      });
    });
  }

  // ── LIVE INDICATOR ─────────────────────────────────────────
  function setPulse(ok) {
    const dot = document.getElementById('pulse-dot');
    const label = document.getElementById('live-label');
    dot.classList.toggle('error', !ok);
    label.textContent = ok ? 'Ao vivo' : 'Offline';
  }

  // ── TOAST ──────────────────────────────────────────────────
  function showToast(msg, type = 'info') {
    const icon = type === 'error' ? '⚠️' : type === 'success' ? '✅' : 'ℹ️';
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.setAttribute('role', 'status');
    el.innerHTML = `<span aria-hidden="true">${icon}</span><span>${msg}</span>`;
    document.getElementById('toast-container').appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  // ── ETA CACHE ──────────────────────────────────────────────
  function setEta(id, info) {
    etaCache[id] = info;
    renderSidebar();
  }
  function getEtaCache(id) { return etaCache[id]; }

  // ── GRADE PÚBLICA (fase 2: rotas/partidas/tarifas — docs §2.1) ──
  function setGrade(rotas) {
    for (const k of Object.keys(gradeCache)) delete gradeCache[k];
    (rotas || []).forEach(r => { gradeCache[r.destino] = r; });
    renderSidebar();
  }
  function getGrade(destino) { return gradeCache[destino]; }

  return {
    setEmbarcacoes(list) { embarcacoes = list; },
    getEmbarcacoes: () => embarcacoes,
    getEmbarcacao: id => embarcacoes.find(e => e.id === id),
    getSelectedId: () => selectedId,
    velocidadeFormatada,
    precoFormatado,
    idadeDoSinal,
    sinalEnvelhecido,
    marcarRecebido,
    renderSidebar,
    bindListClicks,
    bindFilters,
    selectVessel,
    fecharSidebarMobile,
    setPulse,
    showToast,
    setEta,
    getEtaCache,
    setGrade,
    getGrade,
  };
})();
