// ── APP: orquestra polling, ETA e eventos ────────────────────
(function () {
  let apiOk = true;
  let countdown = CONFIG.UPDATE_SEC;

  async function fetchEmbarcacoes() {
    try {
      const dados = await API.listarEmbarcacoes();
      UI.setEmbarcacoes(dados);
      dados.forEach(e => UI.marcarRecebido(e.id));
      MAPA.sincronizarMarcadores(dados);
      UI.renderSidebar();

      if (!apiOk) {
        apiOk = true;
        UI.showToast('Conexão restabelecida com o servidor.', 'success');
        UI.setPulse(true);
      }
    } catch (err) {
      if (apiOk) {
        apiOk = false;
        UI.showToast('Erro ao conectar com a API. Tentando novamente...', 'error');
        UI.setPulse(false);
      }
      // Degradação graciosa: mantém última posição conhecida no mapa (docs §5.3)
    }
  }

  // ETA é secundário: buscamos sob demanda quando há uma embarcação
  // selecionada, sem bloquear o loop principal de 5s.
  async function buscarEta(id) {
    try {
      const info = await API.consultarEta(id, 'Óbidos');
      UI.setEta(id, info);
    } catch (_) {
      /* destino ainda não cadastrado — silencioso por design */
    }
  }

  // Timer de contagem regressiva visível (feedback de "quase tempo real")
  setInterval(() => {
    countdown--;
    if (countdown <= 0) {
      countdown = CONFIG.UPDATE_SEC;
      fetchEmbarcacoes();
    }
    document.getElementById('countdown').textContent = countdown + 's';
  }, 1000);

  // Seleção via sidebar (delegação em UI.bindListClicks)
  UI.bindListClicks(id => {
    const emb = UI.getEmbarcacao(id);
    UI.selectVessel(id, emb);
    if (emb && !UI.getEtaCache(id)) buscarEta(id);
  });

  UI.bindFilters();

  document.getElementById('menu-btn').addEventListener('click', () => {
    const sb = document.getElementById('sidebar');
    const aberto = sb.classList.toggle('open');
    document.getElementById('menu-btn').setAttribute('aria-expanded', String(aberto));
  });

  // Primeira carga
  fetchEmbarcacoes();
})();
