/*
 * DynDisplay Player — écran d'affichage.
 *
 * Rendu adapté de DYNDISPLAY/frontend/src/pages/PostPreview.jsx :
 *   - ZoneSlideshow : une zone = une playlist indépendante (media_playlist),
 *     ordre via display_order, boucle via loop_enabled.
 *   - PdfZone : page par page (~10 s/page, rotation automatique).
 * Différences volontaires vs la préview web (cf. STEP0_ANALYSE.md §3c) :
 *   - Les URLs viennent du cache local (dyndisplay-media://local/<sftp_path>),
 *     pas de l'API web `/media/...`.
 *   - Pas de url/pdf_pages dans le config.json FTP : les PDF sont rendus
 *     localement (pdf.js) page par page.
 *   - Durées réelles : IMAGE → duration_seconds (3-60 s) ; VIDEO → durée
 *     native (fin du fichier) ; PDF → ~10 s/page.
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { loadLocalConfig, isConfigured } from './config/localConfig.js';
import {
  buildConn,
  fetchConfig,
  activeZones,
  fingerprint as configFingerprint,
} from './sync/ftpClient.js';
import { syncMediaForConfig, loadSyncedConfig, storeSyncedConfig, mediaCacheUrl, missingMediaCount } from './cache/mediaCache.js';
import { startHeartbeat, stopHeartbeat } from './sync/heartbeat.js';
import SetupScreen from './screens/SetupScreen.jsx';
import { openPdf, renderPdfPageToCanvas } from './pdf/pdfRender.js';

const PDF_PAGE_MS = 10000;

// ────────────────────────────────────────────────────────────────────────────
// PdfZone — adaptation locale de PostPreview.jsx (pages rendues par pdf.js).
// Une page = une image, ~10 s par page, rotation automatique.
// ────────────────────────────────────────────────────────────────────────────
function PdfZone({ media, className, style, onComplete }) {
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(0);
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const pdfRef = useRef(null);
  const numPagesRef = useRef(0);
  const pageRef = useRef(0);
  const completeRef = useRef(false);
  const onCompleteRef = useRef(onComplete);

  onCompleteRef.current = onComplete;

  useEffect(() => {
    numPagesRef.current = numPages;
  }, [numPages]);

  // Fermeture du document PDF au démontage.
  useEffect(() => () => {
    if (pdfRef.current) pdfRef.current.destroy?.();
    pdfRef.current = null;
  }, []);

  // Chargement du document (via cache local dyndisplay-media://).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(mediaCacheUrl(media.filename));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.arrayBuffer();
        const pdf = await openPdf(data);
        if (cancelled) { pdf.destroy?.(); return; }
        pdfRef.current = pdf;
        completeRef.current = false;
        pageRef.current = 0;
        setCurrentPage(0);
        setNumPages(pdf.numPages || 0);
      } catch (err) {
        if (!cancelled) setNumPages(0);
      }
    })();
    return () => { cancelled = true; };
  }, [media.media_id]);

  // Rotation automatique des pages (~10 s/page), puis signal de fin de média.
  useEffect(() => {
    if (numPages <= 1) return;
    const interval = setInterval(() => {
      const next = pageRef.current + 1;
      if (next >= numPagesRef.current) {
        clearInterval(interval);
        if (!completeRef.current) {
          completeRef.current = true;
          onCompleteRef.current?.();
        }
        return;
      }
      pageRef.current = next;
      setCurrentPage(next);
    }, PDF_PAGE_MS);
    return () => clearInterval(interval);
  }, [numPages]);

  // Rendu de la page courante dans le canvas (taille du conteneur).
  useEffect(() => {
    if (!pdfRef.current || numPages <= 0 || currentPage < 0 || currentPage >= numPages) return;
    const canvas = canvasRef.current;
    const box = containerRef.current;
    if (!canvas || !box) return;
    const { clientWidth: w, clientHeight: h } = box;
    if (!w || !h) return;
    renderPdfPageToCanvas(pdfRef.current, currentPage + 1, canvas, w, h).catch(() => {});
  }, [currentPage, numPages]);

  const displayPage = Math.min(currentPage, Math.max(numPages - 1, 0));

  if (!numPages) {
    return (
      <div className={`zone-pdf ${className}`} style={style}>
        <div className="zone-pdf-placeholder">PDF (chargement…)</div>
      </div>
    );
  }

  return (
    <div className={`zone-pdf ${className}`} style={style} ref={containerRef}>
      <canvas ref={canvasRef} className="zone-pdf-canvas" />
      {numPages > 1 && (
        <span className="zone-badge zone-badge-left">
          {displayPage + 1}/{numPages}
        </span>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// VideoZone — UN seul élément <video> par zone, réutilisé pour chaque média
// de la playlist. Évite de créer un WebMediaPlayer Chromium à chaque
// changement de média (limite ~32 simultanés → erreur "too many
// WebMediaPlayers") et libère le player au démontage.
// ────────────────────────────────────────────────────────────────────────────
function VideoZone({ url, mediaId, onEnded, onError, className, style }) {
  const videoRef = useRef(null);
  const onEndedRef = useRef(onEnded);
  const onErrorRef = useRef(onError);
  onEndedRef.current = onEnded;
  onErrorRef.current = onError;

  // Changement de média : on réutilise l'élément, on recharge la nouvelle source.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.src = url;
    video.load();
    const p = video.play();
    if (p && typeof p.catch === 'function') p.catch(() => {});
  }, [url, mediaId]);

  // Démontage : relâche immédiatement le player Chromium.
  useEffect(() => () => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.removeAttribute('src');
    video.load();
  }, []);

  return (
    <video
      ref={videoRef}
      autoPlay
      muted
      playsInline
      className="zone-media"
      style={style}
      onEnded={() => onEndedRef.current?.()}
      onError={() => onErrorRef.current?.()}
    />
  );
}

// ────────────────────────────────────────────────────────────────────────────
// ZoneSlideshow — playlist indépendante par zone.
// ────────────────────────────────────────────────────────────────────────────
function ZoneSlideshow({ zone, zoneNumber, zoneStyle, overlays, loopEnabled, onNeedMedia }) {
  const playlist = useMemo(
    () =>
      (zone?.media_playlist || (zone?.media ? [zone.media] : []))
        .filter((m) => m && m.media_id)
        .sort((a, b) => (a.display_order || 0) - (b.display_order || 0)),
    [zone],
  );

  const [currentIndex, setCurrentIndex] = useState(0);
  const [mediaAvailable, setMediaAvailable] = useState(true);
  const currentIndexRef = useRef(0);
  const timerRef = useRef(null);
  const playlistKey = playlist.map((m) => m.media_id).join(',');
  const onNeedMediaRef = useRef(onNeedMedia);
  onNeedMediaRef.current = onNeedMedia;

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const advance = useCallback(() => {
    clearTimer();
    const next = currentIndexRef.current + 1;
    if (next >= playlist.length) {
      if (loopEnabled) {
        currentIndexRef.current = 0;
        setCurrentIndex(0);
      }
      // sinon : on reste sur le dernier média affiché.
      return;
    }
    currentIndexRef.current = next;
    setCurrentIndex(next);
  }, [playlist.length, loopEnabled, clearTimer]);

  useEffect(() => {
    currentIndexRef.current = 0;
    setCurrentIndex(0);
    clearTimer();
  }, [playlistKey]);

  const current = playlist[currentIndex] || null;

  // Vérifie que le fichier du média est présent en cache avant de monter
  // <img>/<video>/. Un média absent ne crée pas de WebMediaPlayer (sinon
  // Chromium bloque après ~32 players) et déclenche une re-synchronisation.
  useEffect(() => {
    if (!current) { setMediaAvailable(true); return; }
    let cancelled = false;
    let iv = null;
    const check = async () => {
      try {
        const ok = await window.dyndisplay?.cache?.mediaExists?.(current.filename);
        return ok === true;
      } catch (err) {
        return true; // pont indisponible → on tente l'affichage quand même.
      }
    };
    (async () => {
      try {
        const avail = await check();
        if (cancelled) return;
        setMediaAvailable(avail);
        if (avail) return;
        try { onNeedMediaRef.current?.(current.filename); } catch (err) { /* ignore */ }
        // Re-test toutes les 5 s : dès que le fichier est téléchargé, on affiche.
        iv = setInterval(() => {
          if (cancelled) { clearInterval(iv); return; }
          check()
            .then((ok) => {
              if (!cancelled && ok) { setMediaAvailable(true); clearInterval(iv); }
            })
            .catch(() => {});
        }, 5000);
      } catch (err) {
        if (!cancelled) setMediaAvailable(true);
      }
    })();
    return () => { cancelled = true; if (iv) clearInterval(iv); };
  }, [current?.media_id]);

  useEffect(() => {
    if (!current) return;
    const isImage = current.media_type === 'IMAGE';
    let seconds = null;
    if (isImage) seconds = Math.max((parseInt(current.duration_seconds, 10) || 10), 3);
    else if (!mediaAvailable) seconds = 3; // absent du cache : reprise rapide et cadrée
    if (seconds === null) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      const next = currentIndexRef.current + 1;
      if (next >= playlist.length && !loopEnabled) return; // stop sur le dernier
      advance();
    }, seconds * 1000);
    return clearTimer;
  }, [currentIndex, current, mediaAvailable, playlist.length, loopEnabled, advance, clearTimer]);

  if (!playlist.length) {
    return (
      <div className="zone zone-empty" style={zoneStyle}>
        <div className="zone-empty-label">Zone {zoneNumber}</div>
        {overlays && <div className="zone-badge zone-badge-right">Z-{zoneNumber}</div>}
      </div>
    );
  }
  if (!current) {
    return (
      <div className="zone zone-empty" style={zoneStyle}>
        <div className="zone-empty-label">Zone {zoneNumber}</div>
        {overlays && <div className="zone-badge zone-badge-right">Z-{zoneNumber}</div>}
      </div>
    );
  }

  const mediaUrl = mediaCacheUrl(current.filename);
  const isVideo = current.media_type === 'VIDEO';
  const isPdf = current.media_type === 'PDF';

  if (!mediaAvailable) {
    return (
      <div className="zone" style={zoneStyle}>
        <div className="zone-pdf-placeholder">{current.media_type} (téléchargement…)</div>
        {overlays && playlist.length > 1 && (
          <span className="zone-badge zone-badge-left">
            {((currentIndex % playlist.length) + 1)}/{playlist.length}
          </span>
        )}
        {overlays && (
          <span className="zone-badge zone-badge-right">Z-{zoneNumber}</span>
        )}
      </div>
    );
  }

  return (
    <div className="zone" style={zoneStyle}>
      {isVideo ? (
        <VideoZone
          key={`v-${zoneNumber}`}
          url={mediaUrl}
          mediaId={current.media_id}
          onEnded={advance}
          onError={advance}
          className="zone-media"
        />
      ) : isPdf ? (
        <PdfZone
          key={`p-${zoneNumber}-${current.media_id}`}
          media={current}
          className="zone-pdf-wrap"
          onComplete={advance}
        />
      ) : (
        <img
          key={`i-${zoneNumber}-${current.media_id}`}
          src={mediaUrl}
          alt={current.name || ''}
          className="zone-media"
          onError={advance}
        />
      )}
      {overlays && playlist.length > 1 && (
        <span className="zone-badge zone-badge-left">
          {((currentIndex % playlist.length) + 1)}/{playlist.length}
        </span>
      )}
      {overlays && (
        <span className="zone-badge zone-badge-right">Z-{zoneNumber}</span>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Application
// ────────────────────────────────────────────────────────────────────────────
const ZONE_COLORS = [
  'rgba(59,130,246,0.20)',
  'rgba(16,185,129,0.20)',
  'rgba(245,158,11,0.20)',
  'rgba(239,68,68,0.20)',
  'rgba(168,85,247,0.20)',
  'rgba(20,184,166,0.20)',
  'rgba(244,114,182,0.20)',
  'rgba(99,102,241,0.20)',
];

export default function App() {
  const [phase, setPhase] = useState('loading'); // loading | setup | player
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [localCfg, setLocalCfg] = useState(null);
  const [config, setConfig] = useState(null); // config.json synchronisé (source d'affichage)
  const [status, setStatus] = useState({});
  const [syncing, setSyncing] = useState(false);

  const cfgRef = useRef(null);
  const configRef = useRef(null);
  const fingerprintRef = useRef('');
  const busyRef = useRef(false);

  cfgRef.current = localCfg;
  configRef.current = config;

  const setOverlays = useCallback((v) => setLocalCfg((c) => ({ ...c, showOverlays: v })), []);

  // ── Chargement initial ────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      const cfg = await loadLocalConfig();
      const last = await loadSyncedConfig();
      cfgRef.current = cfg;
      if (last) {
        configRef.current = last;
        fingerprintRef.current = configFingerprint(last);
        setConfig(last);
      }
      if (isConfigured(cfg)) {
        setLocalCfg(cfg);
        setPhase('player');
      } else {
        setLocalCfg(cfg);
        setPhase('setup');
      }
    })();
  }, []);

  // ── Script de synchronisation ─────────────────────────────────────────────
  const runSync = useCallback(async (opts = {}) => {
    const cfg = cfgRef.current;
    if (!cfg || !isConfigured(cfg) || busyRef.current) return { ok: false };
    busyRef.current = true;
    setSyncing(true);
    try {
      const res = await fetchConfig(cfg, fingerprintRef.current);
      if (!res.ok) {
        setStatus((s) => ({ ...s, sync: { ok: false, error: res.error || 'SFTP indisponible' } }));
        return res;
      }
      const conn = buildConn(cfg);
      await storeSyncedConfig(res.config);
      // Re-synchronise les médias si la config a changé OU si des fichiers
      // référencés manquent encore en cache (sync précédent partiellement échoué).
      const missing = await missingMediaCount(res.config);
      if (res.changed || missing > 0) {
        const stats = await syncMediaForConfig(conn, cfg.postCode.trim(), res.config);
        fingerprintRef.current = res.fingerprint;
        setConfig(res.config);
        setStatus((s) => ({
          ...s,
          sync: {
            ok: true,
            detail: `Config ${res.config.code} — ${stats.downloaded} téléchargé(s), ${stats.uptodate} à jour, ${stats.failed} échec(s)${missing > 0 ? ` (${missing} manquant(s))` : ''}`,
          },
        }));
        return { ok: true, changed: true, stats };
      }
      setStatus((s) => ({ ...s, sync: { ok: true, detail: 'Aucun changement détecté' } }));
      return res;
    } catch (err) {
      setStatus((s) => ({ ...s, sync: { ok: false, error: err.message } }));
      return { ok: false, error: err.message };
    } finally {
      busyRef.current = false;
      setSyncing(false);
    }
  }, []);

  // ── Lancement du mode player ──────────────────────────────────────────────
  useEffect(() => {
    if (phase !== 'player') return;
    // Sync immédiate au démarrage.
    runSync();
    // Poll périodique : détecte la fin d'une synchro serveur (immédiate ou
    // programmée via sync_jobs.scheduled_at) dans les ~pollIntervalSec.
    const intervalSec = Math.max(parseInt(cfgRef.current?.pollIntervalSec, 10) || 60, 15);
    const poll = setInterval(() => runSync(), intervalSec * 1000);
    // Synchro quotidienne programmée (heure locale configurable, défaut 02:00).
    let dailyTimer = null;
    const scheduleDaily = () => {
      const time = (cfgRef.current?.syncTime || '02:00');
      const [h, m] = time.split(':').map(Number);
      const now = new Date();
      const target = new Date(now);
      target.setHours(isNaN(h) ? 2 : h, isNaN(m) ? 0 : m, 0, 0);
      if (target <= now) target.setDate(target.getDate() + 1);
      const delay = target.getTime() - now.getTime();
      dailyTimer = setTimeout(() => {
        runSync();
        scheduleDaily();
      }, delay);
    };
    if (cfgRef.current?.syncTime) scheduleDaily();
    // Heartbeat toutes les 60 s (seuil offline serveur 90 s).
    startHeartbeat({
      getLocalConfig: () => cfgRef.current,
      getPostId: () => configRef.current?.post_id || null,
      onStatus: (hb) => setStatus((s) => ({ ...s, heartbeat: hb })),
    });
    return () => {
      clearInterval(poll);
      if (dailyTimer) clearTimeout(dailyTimer);
      stopHeartbeat();
    };
  }, [phase]);

  // ── Raccourci caché : Ctrl+Alt+Shift+P (géré dans electron/main.js) ──────
  useEffect(() => {
    window.dyndisplay?.app?.onOpenSettings(() => {
      setSettingsOpen(true);
    });
  }, []);

  // Re-sync immédiate (mais cadencée) quand un média manque en cache.
  const lastNeedSyncRef = useRef(0);
  const onNeedMedia = useCallback(() => {
    const now = Date.now();
    if (now - lastNeedSyncRef.current > 8000) {
      lastNeedSyncRef.current = now;
      runSync();
    }
  }, [runSync]);

  // ── Persistance des préférences d'affichage ───────────────────────────────
  useEffect(() => {
    if (phase === 'player' && localCfg) {
      window.dyndisplay.config.set(localCfg).catch(() => {});
    }
  }, [localCfg]);

  const handleSaved = useCallback(async (cfg) => {
    const saved = await window.dyndisplay.config.set(cfg);
    setLocalCfg(saved);
    setSettingsOpen(false);
    if (!isConfigured(saved)) {
      setPhase('setup');
      return;
    }
    setPhase('player');
    // (Re)lancé par l'effet [phase].
  }, []);

  // ── Rendu ─────────────────────────────────────────────────────────────────
  if (phase === 'loading') {
    return <div className="boot">DynDisplay Player — initialisation…</div>;
  }

  if (phase === 'setup') {
    return (
      <SetupScreen
        initial={localCfg}
        onSaved={handleSaved}
        standalone
      />
    );
  }

  const layout = config?.layout || null;
  const layoutZones = layout?.zones || [];
  const hasLayout = layoutZones.length > 0;
  const displayEnabled = config?.display_enabled !== false;
  const overlays = cfgRef.current?.showOverlays !== false;
  const zoneList = activeZones(config);

  const problemStatus = () => {
    const s = status || {};
    const problems = [];
    if (s.heartbeat && !s.heartbeat.ok) problems.push('Heartbeat : échec');
    if (s.sync && !s.sync.ok) problems.push(`Sync : ${s.sync.error || 'échec'}`);
    return problems;
  };

  return (
    <div className="stage">
      <div className="stage-backdrop" />

      {!displayEnabled ? (
        <div className="display-disabled">Affichage désactivé</div>
      ) : !hasLayout ? (
        <div className="no-layout">
          <p className="no-layout-title">Aucun layout assigné à ce poste.</p>
          <p className="no-layout-sub">Configurez l'affichage depuis la console DynDisplay.</p>
        </div>
      ) : (
        <div className="stage-canvas">
          {zoneList.map((zone, i) => {
            const lz = layoutZones.find((z) => z.zone_number === zone.zone_number) || {};
            const color = ZONE_COLORS[i % ZONE_COLORS.length];
            const zoneStyle = {
              left: `${lz.position_x ?? 0}%`,
              top: `${lz.position_y ?? 0}%`,
              width: `${lz.width ?? 100}%`,
              height: `${lz.height ?? 100}%`,
              backgroundColor: overlays ? color : 'transparent',
            };
            return (
              <ZoneSlideshow
                key={zone.zone_number}
                zone={zone}
                zoneNumber={zone.zone_number}
                zoneStyle={zoneStyle}
                overlays={overlays}
                loopEnabled={config?.loop_enabled !== false}
                onNeedMedia={onNeedMedia}
              />
            );
          })}
        </div>
      )}

      {settingsOpen && (
        <SetupScreen
          initial={cfgRef.current}
          onSaved={handleSaved}
          onCancel={() => setSettingsOpen(false)}
          overlays={overlays}
          onToggleOverlays={setOverlays}
          onSyncNow={() => runSync()}
          syncing={syncing}
          syncStatus={status?.sync}
        />
      )}

      {problemStatus().length > 0 && (
        <div className="status-bar">
          <span className="status-dot" />
          {problemStatus().join(' · ')}
        </div>
      )}

      {syncing && phase === 'player' && !settingsOpen && (
        <div className="syncing-pill">Synchronisation…</div>
      )}
    </div>
  );
}