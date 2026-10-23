// ── CAMADA DE API ───────────────────────────────────────────
// Todo acesso à rede passa por aqui. Quando polling for substituído por
// WebSocket/SSE, apenas este módulo muda — a UI permanece intacta.
window.API = (function () {
  async function getJson(path) {
    const resp = await fetch(CONFIG.API_BASE + path);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  return {
    // Lista completa de embarcações com posição atual
    listarEmbarcacoes: () => getJson('/embarcacoes'),

    // ETA até um destino nomeado (endpoint novo — docs §5.2)
    consultarEta: (id, destino) =>
      getJson(`/embarcacoes/${id}/eta?destino=${encodeURIComponent(destido)}`),

    // Consulta assíncrona para atualização suave dos marcadores,
    // sem esperar o próximo tick de 5s do polling principal.
    posicoes: () => getJson('/posicoes'),
  };
})();
