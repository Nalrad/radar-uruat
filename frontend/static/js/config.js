// ── CONFIG ──────────────────────────────────────────────────
// Constantes centralizadas (docs/VISAO_PRODUTO.md §5.7).
// A URL da API pode ser sobrescrita via window.__URUA_API_URL__ (ex.:
// injeção do backend ou deploy em outro host) sem editar código.
window.CONFIG = {
  API_BASE: window.__URUA_API_URL__ || 'http://127.0.0.1:8000',
  UPDATE_SEC: 5,          // intervalo de polling (fallback do futuro SSE)
  TRAIL_MAX: 8,           // nº de pontos do rastro
  MAP_CENTER: [-1.77, -55.86],
  MAP_ZOOM: 12,
  SELECT_ZOOM: 14,
  FLY_DURATION: 1,        // segundos
  // Idade máxima do sinal antes de atenuar o ícone (segundos).
  STALE_AFTER_SEC: 30,
};
