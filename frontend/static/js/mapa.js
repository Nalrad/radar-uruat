// ── MAPA: Leaflet, ícones, interpolação suave e popups ──────
window.MAPA = (function () {
  const map = L.map('map', { zoomControl: true }).setView(CONFIG.MAP_CENTER, CONFIG.MAP_ZOOM);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map);

  const iconColors = {
    Transporte: '#3b82f6',
    Turismo:    '#a855f7',
    Pesca:      '#22c55e',
    Carga:      '#f59e0b',
    default:    '#06b6d4',
  };
  const iconEmoji = {
    Transporte: '🚢',
    Turismo:    '⛵',
    Pesca:      '🎣',
    Carga:      '🛳️',
    default:    '⚓',
  };

  // Estado interno dos marcadores
  const markers = {};     // id -> L.Marker
  const animState = {};   // id -> { from, to, start } para interpolação
  const trails = {};      // id -> polyline
  const trailHistory = {};// id -> [[lat,lng], ...]

  function cor(tipo)   { return iconColors[tipo] || iconColors.default; }
  function emoji(tipo) { return iconEmoji[tipo]  || iconEmoji.default; }

  // Ícone orientado pelo rumo (heading), com fade quando sinal envelhece.
  function makeIcon(e, selected = false, stale = false) {
    const size = selected ? 44 : 36;
    const opacidade = stale ? 0.35 : 1;
    const rumo = Number.isFinite(e.rumo) ? e.rumo : 0;
    const html = `
      <div style="
        width:${size}px;height:${size}px;
        background:${cor(e.tipo)};
        border-radius:50% 50% 50% 0;
        transform:rotate(${-45 + rumo}deg);
        opacity:${opacidade};
        border:2px solid rgba(255,255,255,.6);
        display:flex;align-items:center;justify-content:center;
        box-shadow:0 2px 12px rgba(0,0,0,.5);
        transition:opacity .4s;
      ">
        <span style="transform:rotate(${45 - rumo}deg);font-size:${selected ? 18 : 14}px">${emoji(e.tipo)}</span>
      </div>`;
    return L.divIcon({
      html, className: '',
      iconSize:   [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor:[0, -size / 2],
    });
  }

  // Popup responde à "pergunta única" do passageiro: onde está e quando chega.
  function makePopup(e, etaInfo) {
    let etaHtml = '<span style="color:var(--muted)">—</span>';
    if (etaInfo) {
      if (etaInfo.eta_tempo_min != null) {
        etaHtml = `chega em ~${Math.round(etaInfo.eta_tempo_min)} min`;
      } else if (etaInfo.mensagem) {
        etaHtml = etaInfo.mensagem;
      }
    }
    const idade = UI.idadeDoSinal(e);
    return `
      <div class="popup-body">
        <div class="popup-name">${e.nome}</div>
        <div class="popup-grid">
          <div class="popup-item"><label>Tipo</label><span>${e.tipo}</span></div>
          <div class="popup-item"><label>Bandeira</label><span>${e.bandeira}</span></div>
          <div class="popup-item"><label>Velocidade</label><span>${UI.velocidadeFormatada(e.velocidade)}</span></div>
          <div class="popup-item"><label>Rumo</label><span>${Number.isFinite(e.rumo) ? Math.round(e.rumo) + '°' : '—'}</span></div>
          <div class="popup-item wide"><label>ETA · ${etaInfo ? etaInfo.destino : 'destino'}</label><span>${etaHtml}</span></div>
          <div class="popup-item wide"><label>Sinal</label><span>${idade}</span></div>
        </div>
      </div>`;
  }

  // Interpolação suave entre a última posição conhecida e a nova (docs §5.1).
  function setPosicaoSuave(id, lat, lng) {
    const m = markers[id];
    if (!m) return;
    const from = m.getLatLng();
    animState[id] = { from, to: { lat, lng }, start: performance.now(), dur: 1200 };
  }

  function tickAnimacao(now) {
    for (const id in animState) {
      const a = animState[id];
      const t = Math.min((now - a.start) / a.dur, 1);
      const ease = t * (2 - t); // easeOutQuad
      markers[id].setLatLng([
        a.from.lat + (a.to.lat - a.from.lat) * ease,
        a.from.lng + (a.to.lng - a.from.lng) * ease,
      ]);
      if (t >= 1) delete animState[id];
    }
    requestAnimationFrame(tickAnimacao);
  }
  requestAnimationFrame(tickAnimacao);

  function updateTrail(id, lat, lng) {
    if (!trailHistory[id]) trailHistory[id] = [];
    trailHistory[id].push([lat, lng]);
    if (trailHistory[id].length > CONFIG.TRAIL_MAX) trailHistory[id].shift();

    if (trails[id]) map.removeLayer(trails[id]);
    if (trailHistory[id].length > 1) {
      const e = UI.getEmbarcacao(id);
      trails[id] = L.polyline(trailHistory[id], {
        color: cor(e ? e.tipo : 'default'), weight: 2, opacity: 0.5, dashArray: '4 6',
      }).addTo(map);
    }
  }

  // Atualiza/cria marcadores a partir da lista vinda da API.
  // IMPORTANTE: nunca mexe na viewport aqui — o usuário escolheu aquele recorte.
  function sincronizarMarcadores(embarcacoes) {
    embarcacoes.forEach(e => {
      const stale = UI.sinalEnvelhecido(e);
      updateTrail(e.id, e.latitude, e.longitude);

      if (!markers[e.id]) {
        markers[e.id] = L.marker([e.latitude, e.longitude], {
          icon: makeIcon(e, e.id === UI.getSelectedId()),
        })
          .addTo(map)
          .bindPopup(makePopup(e, UI.getEtaCache(e.id)), { maxWidth: 240 })
          .on('click', () => UI.selectVessel(e.id));
      } else {
        setPosicaoSuave(e.id, e.latitude, e.longitude);
        markers[e.id].setIcon(makeIcon(e, e.id === UI.getSelectedId(), stale));
        markers[e.id].setPopupContent(makePopup(e, UI.getEtaCache(e.id)));
      }
    });
  }

  function focarEmbarcacao(e) {
    map.flyTo([e.latitude, e.longitude], CONFIG.SELECT_ZOOM, { duration: CONFIG.FLY_DURATION });
    markers[e.id]?.openPopup();
  }

  return { sincronizarMarcadores, focarEmbarcacao, makeIcon };
})();
