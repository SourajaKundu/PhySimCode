/* PhySimCode project page */
(() => {
  // Fill these in when available; the buttons enable themselves automatically.
  const LINKS = { paper: '', code: '' };

  const P = window.PAPER;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const h = (tag, attrs = {}, html = '') => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'style' && typeof v === 'object') for (const [p, x] of Object.entries(v)) { if (p.startsWith('--')) e.style.setProperty(p, x); else e.style[p] = x; }
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v);
    }
    if (html) e.innerHTML = html;
    return e;
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const cache = {};
  const getJSON = url => (cache[url] ??= fetch(url).then(r => { if (!r.ok) throw new Error(url); return r.json(); }));
  const pretty = s => s.replace(/_/g, ' ').replace(/\b(\d)d\b/gi, '$1D').replace(/\bvs\b/g, 'vs.')
    .replace(/\bu tube\b/i, 'U-tube').replace(/^./, c => c.toUpperCase());
  const fmt = x => {
    if (typeof x !== 'number' || !isFinite(x)) return esc(x);
    if (Number.isInteger(x)) return String(x);
    const a = Math.abs(x);
    if (a !== 0 && (a >= 1e5 || a < 1e-3)) return x.toExponential(3);
    return String(+x.toPrecision(4));
  };
  const domColor = d => (P.DOMAINS[d] || {}).color || '#888';
  const M = id => P.M[id] || { name: id, color: '#888', group: 'open' };

  // ---------- links ----------
  for (const [k, url] of Object.entries(LINKS)) {
    const b = $('#btn-' + k);
    if (b && url) { b.href = url; b.target = '_blank'; b.classList.remove('disabled'); b.querySelector('small')?.remove(); }
    else b?.addEventListener('click', e => e.preventDefault());
  }

  // ---------- Chart.js defaults ----------
  Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = '#4a5068';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.tooltip.backgroundColor = '#1a1d2e';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.maintainAspectRatio = false;
  const grid = { color: '#eef0f6' };
  const alpha = (hex, a) => hex + Math.round(a * 255).toString(16).padStart(2, '0');

  // Lazily create charts when their container first becomes visible (tabs, scrolling).
  const lazyCharts = [];
  const lazy = (canvasSel, make) => {
    const c = $(canvasSel); if (!c) return;
    const item = { c, make, chart: null };
    lazyCharts.push(item);
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting && !item.chart && c.offsetParent) { item.chart = make(c); io.disconnect(); }
    }), { rootMargin: '200px' });
    io.observe(c);
    return item;
  };
  const refreshLazy = () => lazyCharts.forEach(it => {
    if (!it.chart && it.c.offsetParent) { it.chart = it.make(it.c); }
  });

  // ---------- tabs ----------
  $$('.tabs[data-tabs]').forEach(tabs => {
    const root = tabs.parentElement;
    tabs.addEventListener('click', e => {
      const b = e.target.closest('.tab'); if (!b) return;
      $$('.tab', tabs).forEach(t => t.classList.toggle('active', t === b));
      $$('.tab-panel', root).forEach(p => p.classList.toggle('active', p.dataset.panel === b.dataset.tab));
      requestAnimationFrame(refreshLazy);
    });
  });
  const segHandler = (sel, fn) => {
    const s = $(sel); if (!s) return;
    s.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      $$('button', s).forEach(x => x.classList.toggle('active', x === b));
      fn(b);
    });
  };

  // ---------- nav highlight ----------
  const navLinks = $$('.nav-links a');
  const secIO = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id));
  }), { rootMargin: '-45% 0px -50% 0px' });
  navLinks.forEach(a => { const s = $(a.getAttribute('href')); s && secIO.observe(s); a.addEventListener('click', () => document.body.classList.remove('nav-open')); });

  // ---------- autoplay only when visible ----------
  const vidIO = new IntersectionObserver(es => es.forEach(e => {
    const v = e.target;
    if (e.isIntersecting) { if (v.dataset.paused !== '1') v.play().catch(() => {}); }
    else v.pause();
  }), { rootMargin: '100px' });
  const autoVideo = (src, cls) => {
    const v = h('video', { muted: '', loop: '', playsinline: '', preload: 'metadata', class: cls || '' });
    v.muted = true; v.src = src; vidIO.observe(v); return v;
  };

  // ---------- data ----------
  const galleryP = getJSON('data/gallery.json');
  const hardP = getJSON('data/hard.json');

  // ---------- stats count-up ----------
  const statIO = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    statIO.unobserve(e.target);
    const b = e.target, end = +b.dataset.count, t0 = performance.now();
    const step = t => { const p = Math.min(1, (t - t0) / 1200), v = Math.round(end * (1 - Math.pow(1 - p, 3))); b.textContent = v.toLocaleString(); if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }));
  $$('[data-count]').forEach(b => statIO.observe(b));

  // ---------- animated demo ----------
  const demoP = getJSON('data/demo.json');
  const hl = (text, lang) => { try { return hljs.highlight(text, { language: lang }).value; } catch { return esc(text); } };
  Promise.all([demoP, galleryP]).then(([d, g]) => initDemo(d, g));

  function initDemo(D, gallery) {
    const stage = $('#demo-stage'), cap = $('#demo-caption');
    const dpIn = $('#dp-in'), dpMid = $('#dp-mid'), dpOut = $('#dp-out');
    const vIn = $('#demo-in'), vGen = $('#demo-gen'), genWrap = $('.gen-wrap', dpOut);
    const edCot = $('#ed-cot code'), edCode = $('#ed-code code'), edTerm = $('#ed-term');
    const mllm = $('#mllm'), score = $('#scorecard'), finale = $('#demo-finale'), flyers = $('#flyer-layer');
    const pe = D.param_eval, gtNames = Object.keys(D.gt_params || {});
    const okSet = new Set((pe.matched || []).filter(m => m.within_20pct).map(m => m.gt_name));
    const avg = a => a.reduce((x, y) => x + y, 0) / a.length;
    const lawEq = avg(D.scores.law_equivalence);
    const pc = D.pred_cot || {};
    const slimParams = Object.fromEntries(Object.entries(pc.parameters || {}).map(([k, v]) => [k, v && typeof v === 'object' ? `${v.value}${v.unit ? ' ' + v.unit : ''}` : v]));
    const cotText = JSON.stringify({ simulation: pc.simulation, physical_law: pc.physical_law, parameters: slimParams }, null, 2);
    const codeText = D.pred_code || '';
    const termText = `$ python simulation.py\n  integrating dynamics (6 balls, walls, restitution) …\n  rendering frames → video.mp4 …\n✓ done in ${(3.1).toFixed(1)} s · video.mp4 written`;
    const FIN_K = ['multi_physics_arena', 'domino_chain', 'tumbling_dice', 'trebuchet_throw'];
    const FIN_S = ['billiards_break', 'three_gear_chain', 'rolling_race_hoop_vs_disk_vs_sphere', 'slab_springs_block_drop'];
    const byExp = Object.fromEntries(gallery.map(x => [x.experiment, x]));
    FIN_K.flatMap((k, i) => [k, FIN_S[i]]).forEach((exp, i) => {
      const x = byExp[exp]; if (!x) return;
      const it = h('div', { class: 'fin-item', style: { transitionDelay: i * 90 + 'ms' }, onclick: () => openSample(x) });
      const v = h('video', { muted: '', loop: '', playsinline: '', preload: 'none', poster: `videos/posters/${exp}.jpg` }); v.muted = true; v.dataset.src = `videos/gallery/${exp}.mp4`;
      it.append(v, h('span', { class: x.engine === 'scipy' ? 'k2' : 'k3' }, x.engine === 'scipy' ? '2D · SciPy' : '3D · PyBullet'));
      finale.append(it);
    });

    // virtual clock: everything is timed against `vt`, which only advances while playing
    let vt = 0, last = null, playing = false, runId = 0, cur = 0, stepStart = 0, started = false, inView = false;
    const waiters = new Set(), frameFns = new Set();
    const CANCEL = Symbol('cancel');
    const loop = t => {
      if (last !== null && playing) vt += Math.min(64, t - last);
      last = t;
      if (playing) {
        frameFns.forEach(f => f());
        waiters.forEach(w => { if (vt >= w.until) { waiters.delete(w); w.resolve(); } });
        const bar = $$('.dstep span', $('#demo-steps'));
        bar.forEach((b, i) => { b.style.width = i < cur ? '100%' : i > cur ? '0%' : Math.min(100, (vt - stepStart) / STEPS[cur].dur * 100) + '%'; });
      }
      requestAnimationFrame(loop);
    };
    const wait = (ms, id) => new Promise((resolve, reject) => {
      if (id !== runId) return reject(CANCEL);
      const w = { until: vt + ms, resolve: () => (id === runId ? resolve() : reject(CANCEL)) };
      waiters.add(w);
    });
    const typeInto = (el, text, ms, lang, id) => new Promise((resolve, reject) => {
      const t0 = vt; let lastN = -1;
      const f = () => {
        if (id !== runId) { frameFns.delete(f); return reject(CANCEL); }
        const n = Math.min(text.length, Math.floor(text.length * (vt - t0) / ms));
        if (n !== lastN) {
          lastN = n;
          el.innerHTML = (lang ? hl(text.slice(0, n), lang) : esc(text.slice(0, n))) + (n < text.length ? '<span class="caret"></span>' : '');
          el.parentElement.scrollTop = el.parentElement.scrollHeight;
        }
        if (n >= text.length) { frameFns.delete(f); resolve(); }
      };
      frameFns.add(f);
    });
    const setTab = t => { $$('.ed-tab', dpMid).forEach(x => x.classList.toggle('on', x.dataset.t === t)); [['cot', '#ed-cot'], ['code', '#ed-code'], ['term', '#ed-term']].forEach(([k, s]) => $(s).classList.toggle('on', k === t)); };
    const focus = el => [dpIn, dpMid, dpOut].forEach(x => x.classList.toggle('focus', x === el));
    const restartVideos = () => [vIn, vGen].forEach(v => { v.currentTime = 0; if (playing) v.play().catch(() => {}); });
    const scoreCards = () => {
      const chips = gtNames.map(n => `<i class="${okSet.has(n) ? 'ok' : ''}">${esc(n)} ${okSet.has(n) ? '✓' : '✗'}</i>`).join('');
      const ok = okSet.size, row = (h1, val, body) => `<div class="sc"><div class="sc-h">${h1}<b>${val}</b></div>${body}</div>`;
      return row('Physical law', `${lawEq.toFixed(1)} / 5`, `<div class="sc-bar"><span data-w="${lawEq / 5 * 100}" style="background:#8c7ae6"></span></div><div class="sc-note">3 LLM judges: does it match the law in the video?</div>`) +
        row('Parameters within ±20%', `${ok} / ${gtNames.length}`, `<div class="sc-params">${chips}</div>`) +
        row('Video similarity', `${D.scores.dino.toFixed(2)} · ${D.scores.xclip.toFixed(2)}`, `<div class="sc-bar"><span data-w="${D.scores.dino * 100}" style="background:#e8707a"></span></div><div class="sc-note">DINOv2 · VideoCLIP cosine vs. the input</div>`) +
        row('Code', D.scores.runs ? 'runs ✓' : 'crashes ✗', '<div class="sc-note">compiles, runs, and writes video.mp4</div>');
    };
    const showCards = async (instant, id) => {
      score.innerHTML = scoreCards();
      const cards = $$('.sc', score);
      for (const c of cards) {
        if (!instant) await wait(650, id);
        c.classList.add('on'); $$('[data-w]', c).forEach(b => (b.style.width = b.dataset.w + '%'));
      }
    };
    const fly = () => {
      const sr = stage.getBoundingClientRect(), vr = vIn.getBoundingClientRect(), mr = mllm.getBoundingClientRect();
      for (let i = 0; i < 6; i++) {
        const im = h('img', { class: 'flyer', src: `videos/demo/frame${i}.jpg`, alt: '' });
        const x0 = vr.left - sr.left + (vr.width - 96) * (i / 5), y0 = vr.top - sr.top + vr.height * 0.25;
        im.style.transform = `translate(${x0}px, ${y0}px)`;
        flyers.append(im);
        setTimeout(() => { im.style.transform = `translate(${mr.left - sr.left + mr.width / 2 - 48}px, ${mr.top - sr.top}px) scale(.35)`; im.style.opacity = '0'; }, 120 + i * 200);
        setTimeout(() => im.remove(), 2600 + i * 200);
      }
    };
    const finaleOn = on => {
      finale.classList.toggle('on', on);
      $$('video', finale).forEach(v => { if (on) { if (!v.src) v.src = v.dataset.src; v.play().catch(() => {}); } else v.pause(); });
    };

    const STEPS = [
      { dur: 4200, cap: 'Input: just a video', sub: 'plus the engine name (here: SciPy). Nothing else.',
        run: async (inst, id) => { focus(dpIn); dpMid.classList.add('dim'); dpOut.classList.add('dim'); if (!inst) { restartVideos(); } } },
      { dur: 3600, cap: 'The MLLM watches the frames', sub: '',
        run: async (inst, id) => { dpMid.classList.remove('dim'); focus(dpMid); mllm.classList.add('busy'); setTab('cot'); if (!inst) fly(); } },
      { dur: 7600, cap: 'It infers the physics', sub: 'the governing law and every parameter value, as JSON',
        run: async (inst, id) => { setTab('cot'); if (inst) edCot.innerHTML = hl(cotText, 'json'); else await typeInto(edCot, cotText, 6600, 'json', id); } },
      { dur: 7200, cap: 'It writes the simulation from scratch', sub: 'self-contained Python: NumPy, SciPy, Matplotlib',
        run: async (inst, id) => { setTab('code'); if (inst) edCode.innerHTML = hl(codeText, 'python'); else await typeInto(edCode, codeText, 6400, 'python', id); } },
      { dur: 4600, cap: 'We run the code', sub: 'it renders a brand-new video',
        run: async (inst, id) => {
          setTab('term'); mllm.classList.remove('busy');
          if (inst) edTerm.textContent = termText; else await typeInto(edTerm, termText, 1600, null, id);
          dpOut.classList.remove('dim'); focus(dpOut); genWrap.classList.add('on'); if (!inst) restartVideos();
        } },
      { dur: 6200, cap: 'We score it against the input', sub: 'law · parameters · video · code',
        run: async (inst, id) => { focus(dpOut); await showCards(inst, id); } },
      { dur: 6500, cap: 'Same task: 162 phenomena, 2D and 3D', sub: '14 MLLMs evaluated. Scroll down for the results.',
        run: async (inst, id) => { focus(null); finaleOn(true); } },
    ];
    const bars = $('#demo-steps');
    STEPS.forEach((s, i) => { const b = h('button', { class: 'dstep', style: { '--w': s.dur }, title: s.cap, 'aria-label': `Step ${i + 1}: ${s.cap}` }, '<span></span>'); b.onclick = () => go(i); bars.append(b); });

    const reset = () => {
      waiters.clear(); frameFns.clear(); flyers.innerHTML = '';
      [dpIn, dpMid, dpOut].forEach(x => x.classList.remove('dim', 'focus'));
      mllm.classList.remove('busy'); setTab('cot');
      edCot.innerHTML = ''; edCode.innerHTML = ''; edTerm.textContent = '';
      genWrap.classList.remove('on'); score.innerHTML = ''; finaleOn(false);
    };
    const setCaption = i => {
      cap.innerHTML = `<span class="num">${i + 1}</span>${esc(STEPS[i].cap)}${STEPS[i].sub ? `<span class="sub">${esc(STEPS[i].sub)}</span>` : ''}`;
      cap.classList.remove('swap'); void cap.offsetWidth; cap.classList.add('swap');
    };
    async function go(k) {
      const id = ++runId;
      reset();
      for (let i = 0; i < k; i++) await STEPS[i].run(true, id);
      setPlaying(true);
      try {
        for (let i = k; i < STEPS.length; i++) {
          cur = i; stepStart = vt; setCaption(i);
          const t0 = vt;
          await STEPS[i].run(false, id);
          await wait(Math.max(0, STEPS[i].dur - (vt - t0)), id);
        }
        cur = STEPS.length; setPlaying(false); $('#demo-pause').textContent = '▶';
      } catch (e) { if (e !== CANCEL) throw e; }
    }
    function setPlaying(p) {
      playing = p;
      $('#demo-pause').textContent = p ? '❚❚' : '▶';
      [vIn, vGen].forEach(v => (p && inView ? v.play().catch(() => {}) : v.pause()));
      $$('video', finale).forEach(v => (p && inView && finale.classList.contains('on') ? v.play().catch(() => {}) : v.pause()));
    }
    $('#demo-pause').onclick = () => { if (cur >= STEPS.length) return go(0); setPlaying(!playing); userPaused = !playing; };
    $('#demo-replay').onclick = () => { userPaused = false; go(0); };
    let userPaused = false;
    new IntersectionObserver(es => es.forEach(e => {
      inView = e.isIntersecting;
      if (inView && !started) { started = true; go(0); }
      else if (started && cur < STEPS.length && !userPaused) setPlaying(inView);
    }), { threshold: 0.35 }).observe($('#demo'));
    requestAnimationFrame(loop);
  }

  // ---------- results charts ----------
  const MAIN = P.MAIN;
  const names = ids => ids.map(id => M(id).name);
  const gcol = id => M(id).color;

  let lawsChart, lawsIdx = 5;
  lazy('#chart-laws', c => (lawsChart = new Chart(c, {
    type: 'bar',
    data: {
      labels: names(MAIN),
      datasets: [
        { label: 'Correctness (prior knowledge)', data: MAIN.map(m => P.T3[m][1]), backgroundColor: '#d9dcef', borderRadius: 6, barPercentage: .8 },
        { label: 'Equivalence with video (grounding)', data: MAIN.map(m => P.T3[m][5]), backgroundColor: MAIN.map(gcol), borderRadius: 6, barPercentage: .8 },
      ],
    },
    options: {
      scales: { y: { min: 1, max: 5, grid, title: { display: true, text: 'Likert score (1–5)' } }, x: { grid: { display: false }, ticks: { maxRotation: 40, minRotation: 0, autoSkip: false } } },
      plugins: { tooltip: { callbacks: { afterBody: items => { const m = MAIN[items[0].dataIndex]; const corr = lawsChart.data.datasets[0].data[items[0].dataIndex]; return `Grounding gap: ${(corr - lawsChart.data.datasets[1].data[items[0].dataIndex]).toFixed(2)}`; } } } },
    },
  })));
  segHandler('#laws-sub', b => {
    lawsIdx = +b.dataset.i;
    if (!lawsChart) return;
    const corrIdx = lawsIdx === 4 ? 0 : 1;
    lawsChart.data.datasets[0].data = MAIN.map(m => P.T3[m][corrIdx]);
    lawsChart.data.datasets[0].label = corrIdx === 0 ? 'Correctness – formula (prior knowledge)' : 'Correctness – overall (prior knowledge)';
    lawsChart.data.datasets[1].data = MAIN.map(m => P.T3[m][lawsIdx]);
    lawsChart.data.datasets[1].label = `Equivalence – ${b.textContent.toLowerCase()} (grounding)`;
    lawsChart.update();
  });

  let simChart;
  const simData = k => k === 'human'
    ? { ds: [['Physical plausibility', 0, '#74b84a'], ['Physics equivalence', 1, '#8c7ae6'], ['Appearance equivalence', 2, '#4a9be0']], min: 1, max: 5, t: 'Human Likert (1–5)' }
    : { ds: [['DINOv2 similarity', 3, '#e8707a'], ['VideoCLIP similarity', 4, '#f08c3c']], min: 0.3, max: 0.9, t: 'Cosine similarity' };
  const buildSim = k => {
    const s = simData(k);
    return { labels: names(MAIN), datasets: s.ds.map(([l, i, c]) => ({ label: l, data: MAIN.map(m => P.T4[m][i]), backgroundColor: c, borderRadius: 5 })) };
  };
  lazy('#chart-sim', c => (simChart = new Chart(c, {
    type: 'bar', data: buildSim('human'),
    options: { scales: { y: { min: 1, max: 5, grid, title: { display: true, text: 'Human Likert (1–5)' } }, x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 40 } } } },
  })));
  segHandler('#sim-sub', b => {
    if (!simChart) return;
    const s = simData(b.dataset.k);
    simChart.data = buildSim(b.dataset.k);
    Object.assign(simChart.options.scales.y, { min: s.min, max: s.max }); simChart.options.scales.y.title.text = s.t;
    simChart.update();
  });

  lazy('#chart-code', c => new Chart(c, {
    type: 'line',
    data: {
      labels: ['CoT extracted', 'Code extracted', 'Compiles', 'Runs w/o error', 'Saves video'],
      datasets: MAIN.map(m => ({
        label: M(m).name, data: P.T5[m].slice(1, 6), borderColor: gcol(m), backgroundColor: gcol(m),
        borderWidth: 2.5, pointRadius: 4, pointHoverRadius: 7, tension: .25, borderDash: M(m).group === 'open' ? [6, 4] : [],
      })),
    },
    options: {
      interaction: { mode: 'nearest', intersect: false },
      scales: { y: { min: 30, max: 100, grid, title: { display: true, text: '% of 2,430 inputs' } }, x: { grid } },
      plugins: { legend: { position: 'right', onHover: (e, item, legend) => { const ch = legend.chart; ch.data.datasets.forEach((d, i) => d.borderWidth = i === item.datasetIndex ? 5 : 1.5); ch.update('none'); }, onLeave: (e, item, legend) => { legend.chart.data.datasets.forEach(d => d.borderWidth = 2.5); legend.chart.update('none'); } }, tooltip: { callbacks: { label: x => ` ${x.dataset.label}: ${x.parsed.y}%` } } },
    },
  }));

  const labelPlugin = {
    id: 'pointLabels',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((ds, i) => {
        if (!ds.pointLabel) return;
        chart.getDatasetMeta(i).data.forEach(pt => {
          ctx.save(); ctx.font = "600 11px 'Plus Jakarta Sans'"; ctx.fillStyle = '#1a1d2e';
          const r = pt.options.radius || 6;
          ctx.fillText(ds.pointLabel, pt.x + r + 4, pt.y + 4); ctx.restore();
        });
      });
    },
  };
  lazy('#chart-param', c => new Chart(c, {
    type: 'bubble',
    data: {
      datasets: MAIN.map(m => ({
        label: M(m).name, pointLabel: `${M(m).name} · ${(P.T9[m][6] * 100).toFixed(1)}%`,
        data: [{ x: P.T9[m][3], y: P.T9[m][4], r: 6 + Math.sqrt(P.T9[m][6]) * 70 }],
        backgroundColor: alpha(gcol(m), .55), borderColor: gcol(m), borderWidth: 2,
      })),
    },
    options: {
      layout: { padding: { right: 120 } },
      scales: {
        x: { min: 0.17, max: 0.49, grid, title: { display: true, text: 'Naming recall (matched / GT params)' } },
        y: { min: 0.12, max: 0.18, grid, title: { display: true, text: 'Value accuracy within ±20% (matched)' } },
      },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: x => { const m = MAIN[x.datasetIndex]; const t = P.T9[m]; return [` ${M(m).name}`, ` naming recall ${t[3]}, value acc ${t[4]}`, ` end-to-end recovery ${(t[6] * 100).toFixed(2)}%`, ` avg params predicted ${t[1]}, parse fails ${t[0]}`]; } } } },
    },
    plugins: [labelPlugin],
  }));

  // full table
  (() => {
    const cols = [
      ['Model', m => M(m).name, null],
      ['Law corr.', m => P.T3[m][1], 1], ['Law eq.', m => P.T3[m][5], 1],
      ['Plausibility', m => P.T4[m][0], 1], ['Physics eq.', m => P.T4[m][1], 1], ['Appearance eq.', m => P.T4[m][2], 1],
      ['DINOv2', m => P.T4[m][3], 1], ['VideoCLIP', m => P.T4[m][4], 1],
      ['Param. acc. %', m => P.T5[m][0], 1], ['Naming recall', m => P.T9[m][3], 1],
      ['Runs w/o error %', m => P.T5[m][4], 1], ['Video save %', m => P.T5[m][5], 1], ['CodeBLEU', m => P.T5[m][6], 1],
    ];
    const tbl = $('#full-table');
    let sortCol = -1, asc = false;
    const ranges = cols.map(([, f, num]) => num ? [Math.min(...MAIN.map(f)), Math.max(...MAIN.map(f))] : null);
    const cell = (ci, m) => {
      const v = cols[ci][1](m);
      if (ci === 0) return `<td><span class="mdot" style="background:${gcol(m)}"></span>${esc(v)}</td>`;
      const [lo, hi] = ranges[ci], t = hi > lo ? (v - lo) / (hi - lo) : 0;
      return `<td style="background:rgba(160,95,130,${(t * .28).toFixed(3)});${t > .97 ? 'font-weight:700' : ''}">${v}</td>`;
    };
    const render = () => {
      let html = '<thead><tr>' + cols.map((c, i) => `<th data-i="${i}" class="${i === sortCol ? 'sorted' + (asc ? ' asc' : '') : ''}">${c[0]}</th>`).join('') + '</tr></thead><tbody>';
      if (sortCol < 0) {
        for (const [g, title] of [['closed', 'Closed-source'], ['open', 'Open-source']]) {
          html += `<tr class="grp"><td colspan="${cols.length}">${title}</td></tr>`;
          MAIN.filter(m => M(m).group === g).forEach(m => { html += '<tr>' + cols.map((_, i) => cell(i, m)).join('') + '</tr>'; });
        }
      } else {
        const f = cols[sortCol][1];
        [...MAIN].sort((a, b) => { const x = f(a), y = f(b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); })
          .forEach(m => { html += '<tr>' + cols.map((_, i) => cell(i, m)).join('') + '</tr>'; });
      }
      tbl.innerHTML = html + '</tbody>';
    };
    tbl.addEventListener('click', e => {
      const th = e.target.closest('th'); if (!th) return;
      const i = +th.dataset.i;
      if (sortCol === i) asc = !asc; else { sortCol = i; asc = i === 0; }
      render();
    });
    render();
  })();

  // kappa
  const KNOTES = {
    physics: 'Patch-wise metrics agree strongly with each other but barely with humans judging whether the regenerated video shows the same physics.',
    appearance: 'Humans rating visual appearance agree more with patch-wise metrics, because both focus on pixel-level match rather than physics.',
    judges: 'Pairwise agreement between the three LLM judges never exceeds 0.85, so the panel is not redundant. 86% of judgments agree within 1 Likert point.',
  };
  const renderKappa = k => {
    const box = $('#kappa-grid'); box.innerHTML = '';
    for (const g of ['closed', 'open']) {
      const card = h('div', { class: 'kcard' }, `<h5><span class="badge ${g}">${g === 'closed' ? 'Closed-source' : 'Open-source'}</span> models, pooled</h5>`);
      for (const [pair, v] of Object.entries(P.KAPPA[k][g])) {
        const col = v > .6 ? '#8c7ae6' : v > .3 ? '#4a9be0' : '#e8707a';
        const row = h('div', { class: 'krow' }, `<span>${pair}</span><div class="kbar"><span style="width:0;background:${col}"></span></div><b>${v.toFixed(3)}</b>`);
        card.append(row);
        requestAnimationFrame(() => requestAnimationFrame(() => { $('.kbar span', row).style.width = Math.max(1, v * 100) + '%'; }));
      }
      box.append(card);
    }
    $('#kappa-note').textContent = KNOTES[k];
  };
  renderKappa('physics');
  segHandler('#kappa-sub', b => renderKappa(b.dataset.k));

  // ---------- frontier charts ----------
  const ALL14 = [...P.FRONTIER, ...MAIN];
  const groupColor = m => ({ frontier: '#d9480f', closed: '#4263eb', open: '#2b8a3e' }[M(m).group]);
  const hbar = (c, valFn, opts = {}) => {
    const ids = [...ALL14].sort((a, b) => valFn(b) - valFn(a));
    return new Chart(c, {
      type: 'bar',
      data: { labels: names(ids), datasets: [{ data: ids.map(valFn), backgroundColor: ids.map(m => alpha(groupColor(m), M(m).group === 'frontier' ? 1 : .5)), borderRadius: 4 }] },
      options: {
        indexAxis: 'y',
        scales: { x: { grid, ...opts.x }, y: { grid: { display: false }, ticks: { font: { size: 11 } } } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: x => ' ' + x.parsed.x + (opts.unit || '') } } },
      },
    });
  };
  lazy('#chart-f-law', c => hbar(c, m => P.T6[m][5], { x: { min: 1, max: 3.2 } }));
  lazy('#chart-f-param', c => hbar(c, m => P.T8[m][0], { x: { min: 0, max: 20 }, unit: '%' }));
  lazy('#chart-f-vid', c => {
    const ids = [...ALL14].sort((a, b) => P.T7[b][0] - P.T7[a][0]);
    return new Chart(c, {
      type: 'bar',
      data: { labels: names(ids), datasets: [
        { label: 'DINOv2', data: ids.map(m => P.T7[m][0]), backgroundColor: ids.map(m => alpha(groupColor(m), M(m).group === 'frontier' ? 1 : .55)), borderRadius: 3 },
        { label: 'VideoCLIP', data: ids.map(m => P.T7[m][1]), backgroundColor: ids.map(m => alpha(groupColor(m), .22)), borderRadius: 3 },
      ] },
      options: { indexAxis: 'y', scales: { x: { min: 0.3, max: 0.95, grid }, y: { grid: { display: false }, ticks: { font: { size: 11 } } } }, plugins: { legend: { display: false } } },
    });
  });

  // ---------- comparator ----------
  const cmp = { detail: null, playing: true, speed: 1 };
  const cmpVideos = () => $$('#comparator video');
  const applyPlayback = () => cmpVideos().forEach(v => {
    v.playbackRate = cmp.speed;
    v.dataset.paused = cmp.playing ? '0' : '1';
    if (cmp.playing) v.play().catch(() => {}); else v.pause();
  });
  $('#cmp-play').addEventListener('click', () => { cmp.playing = !cmp.playing; $('#cmp-play').textContent = cmp.playing ? '❚❚ Pause all' : '▶ Play all'; applyPlayback(); });
  $('#cmp-restart').addEventListener('click', () => { cmpVideos().forEach(v => { v.currentTime = 0; }); applyPlayback(); });
  $('#cmp-speed').addEventListener('change', e => { cmp.speed = +e.target.value; applyPlayback(); });

  const paramSummary = (pe, gtN) => {
    if (!pe || pe.no_record || pe.parse_ok === false) return null;
    return { n: pe.n_within_tolerance ?? 0, matched: pe.n_matched || 0, gt: gtN };
  };

  hardP.then(list => {
    const strip = $('#sample-strip');
    list.forEach((s, i) => {
      const nok = Object.values(s.available).filter(Boolean).length;
      const t = h('div', { class: 'sthumb', onclick: () => selectHard(s, t) },
        `<img src="videos/posters/${s.experiment}.jpg" alt="" loading="lazy"><div>${esc(pretty(s.experiment))}<small>${s.engine === 'scipy' ? 'SciPy 2D' : 'PyBullet 3D'} · #${s.sample_id} · ${nok}/14 videos</small></div>`);
      strip.append(t);
      if (i === 5) selectHard(s, t);
    });
  });

  function selectHard(s, thumb) {
    $$('.sthumb').forEach(t => t.classList.toggle('active', t === thumb));
    const ref = $('#cmp-ref-video');
    ref.src = `videos/hard/${s.tag}/reference.mp4`; vidIO.observe(ref);
    $('#cmp-ref-law').innerHTML = `<b>GT law:</b> ${esc(s.law)}`;
    const nok = Object.values(s.available).filter(Boolean).length;
    $('#cmp-meta').textContent = `${pretty(s.experiment)} · ${s.engine} · sample ${s.sample_id} · ${nok}/14 models produced a video`;
    getJSON(`data/hard/${s.tag}.json`).then(d => {
      cmp.detail = d;
      $('#cmp-ref-open').onclick = () => openGT(d);
      for (const g of ['frontier', 'closed', 'open']) {
        const box = $('#cmp-grid-' + g); box.innerHTML = '';
        Object.keys(d.models).filter(m => M(m).group === g).forEach(m => {
          const md = d.models[m], ps = paramSummary(md.param_eval, Object.keys(d.gt.gt_parameters || {}).length);
          const tile = h('div', { class: 'tile', style: { '--c': M(m).color }, onclick: () => openPred(d, m) });
          if (md.video) tile.append(autoVideo(`videos/hard/${s.tag}/${m}.mp4`));
          else tile.append(h('div', { class: 'failed' }, `<div>✕ Failed<small>no video produced</small></div>`));
          tile.append(h('div', { class: 'tile-label' }, `<span class="mdot" style="background:${M(m).color}"></span>${esc(M(m).name)}`));
          const pills = h('div', { class: 'tile-stats' });
          if (ps && ps.gt) pills.innerHTML = `<span class="pill ${ps.n > 0 ? 'good' : 'bad'}" title="GT parameters named and estimated within ±20%">±20%: ${ps.n}/${ps.gt}</span><span class="pill" title="GT parameters the model named">named ${ps.matched}/${ps.gt}</span>`;
          else pills.innerHTML = `<span class="pill bad">no parsable CoT</span>`;
          tile.append(pills);
          box.append(tile);
        });
      }
      applyPlayback();
    });
  }

  // ---------- CoT rendering ----------
  const FN = new Set(['sin', 'cos', 'tan', 'exp', 'log', 'max', 'min', 'sgn', 'sign', 'atan', 'tanh', 'sinh', 'cosh', 'sqrt']);
  const looksMath = (s, key) => {
    if (!/latex|formula/i.test(key) || !/\\[a-zA-Z]+|\^|_\{/.test(s)) return false;
    if (/(^|[^\\a-zA-Z])[a-zA-Z]+_[a-zA-Z]{2,}/.test(s)) return false;          // e.g. theta_eq (unbraced multi-letter subscript)
    const bare = s.replace(/\\[a-zA-Z]+/g, ' ').replace(/\{[^{}]*\}/g, ' ').match(/\b[a-zA-Z]{3,}\b/g) || [];
    return bare.every(w => FN.has(w));
  };
  const renderMath = s => { try { return `<span class="math">${katex.renderToString(s, { displayMode: false, throwOnError: true, strict: 'ignore' })}</span>`; } catch { return `<code class="mono">${esc(s)}</code>`; } };
  const renderVal = (v, key = '') => {
    if (v === null || v === undefined || v === '') return '<span class="muted">—</span>';
    if (typeof v === 'number' || typeof v === 'boolean') return `<code>${fmt(v)}</code>`;
    if (typeof v === 'string') {
      if (looksMath(v, key)) return renderMath(v);
      if (/python|code|equations?$/i.test(key) && /[=()*]/.test(v)) return `<code class="mono">${esc(v)}</code>`;
      return `<p>${esc(v)}</p>`;
    }
    if (Array.isArray(v)) {
      const tag = /steps/i.test(key) ? 'ol' : 'ul';
      return `<${tag}>` + v.map(x => `<li>${renderVal(x, key).replace(/^<p>|<\/p>$/g, '')}</li>`).join('') + `</${tag}>`;
    }
    if (typeof v === 'object') {
      return '<div class="cot-kv">' + Object.entries(v).map(([k, x]) => `<b>${esc(k.replace(/_/g, ' '))}</b><div>${renderVal(x, k)}</div>`).join('') + '</div>';
    }
    return esc(v);
  };
  const renderCoT = cot => {
    if (!cot || typeof cot !== 'object') return '<p class="muted">No parsable chain-of-thought.</p>';
    return Object.entries(cot).filter(([k]) => k !== 'parameters').map(([k, v]) =>
      `<div class="cot-sec"><div class="ck">${esc(k.replace(/_/g, ' '))}</div>${renderVal(v, k)}</div>`).join('');
  };
  const paramRows = (params, cotParams) => {
    const rows = [];
    const cp = (cotParams && typeof cotParams === 'object') ? cotParams : {};
    const keys = new Set([...Object.keys(params || {}), ...Object.keys(cp)]);
    for (const k of keys) {
      const c = cp[k];
      const val = params && k in params ? params[k] : (c && typeof c === 'object' ? c.value : c);
      const unit = c && typeof c === 'object' ? (c.unit ?? '') : '';
      const desc = c && typeof c === 'object' ? (c.description ?? '') : '';
      rows.push(`<tr><td><code>${esc(k)}</code></td><td class="num">${typeof val === 'object' ? esc(JSON.stringify(val)) : fmt(val)}</td><td>${esc(unit)}</td><td>${esc(desc)}</td></tr>`);
    }
    return `<table class="ptable"><thead><tr><th>Parameter</th><th>Value</th><th>Unit</th><th>Description</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
  };
  const codeBlock = code => {
    const id = 'c' + Math.random().toString(36).slice(2);
    let html = esc(code || '# (no code)');
    try { html = hljs.highlight(code || '', { language: 'python' }).value; } catch {}
    return `<div class="code-wrap"><button class="ctl copy-code" data-copy="#${id}">Copy</button><pre class="code"><code id="${id}" class="hljs language-python">${html}</code></pre></div>`;
  };

  // ---------- modal ----------
  const modal = $('#modal');
  const closeModal = () => { modal.classList.remove('open'); $('#modal-media').innerHTML = ''; document.body.style.overflow = ''; };
  modal.addEventListener('click', e => { if (e.target.closest('[data-close]')) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
  const openModal = ({ head, video, videoNote, tabs }) => {
    $('#modal-head').innerHTML = head;
    const media = $('#modal-media'); media.innerHTML = '';
    if (video) {
      const v = h('video', { controls: '', autoplay: '', muted: '', loop: '', playsinline: '' }); v.muted = true; v.src = video; media.append(v);
    } else media.append(h('div', { class: 'tile' }, '<div class="failed" style="aspect-ratio:4/3"><div>✕ Failed<small>no video produced</small></div></div>'));
    if (videoNote) media.append(h('div', { class: 'mm-note' }, videoNote));
    const tb = $('#modal-tabs'), panels = $('#modal-panels'); tb.innerHTML = ''; panels.innerHTML = '';
    tabs.forEach(([name, html], i) => {
      const b = h('button', { class: 'tab' + (i ? '' : ' active') }, name);
      const p = h('div', { class: 'mpanel' + (i ? '' : ' active') }, html);
      b.onclick = () => { $$('.tab', tb).forEach(x => x.classList.toggle('active', x === b)); $$('.mpanel', panels).forEach(x => x.classList.toggle('active', x === p)); };
      tb.append(b); panels.append(p);
    });
    modal.classList.add('open'); document.body.style.overflow = 'hidden';
    panels.scrollTop = 0;
  };
  const metaTags = x => `<div class="gmeta"><span class="dtag" style="--c:${domColor(x.domain)}">${esc(x.domain)}</span><span class="pill">${x.engine === 'scipy' ? 'SciPy · 2D' : 'PyBullet · 3D'}</span>${x.n_rand ? `<span class="pill">n<sub>rand</sub> = ${x.n_rand}</span>` : ''}${x.samples ? `<span class="pill">${x.samples.toLocaleString()} samples</span>` : ''}<span class="pill">sample #${esc(x.sample_id)}</span></div>`;

  function openSample(x) {
    getJSON(`data/samples/${x.experiment}.json`).then(s => {
      openModal({
        head: `<h3>${esc(pretty(x.experiment))}</h3>${metaTags(x)}`,
        video: `videos/gallery/${x.experiment}.mp4`,
        videoNote: `${esc(x.law)}`,
        tabs: [
          ['Chain-of-thought', renderCoT(s.cot)],
          ['Parameters', paramRows(s.params, s.cot && s.cot.parameters)],
          ['Simulation code', codeBlock(s.code)],
          ['Raw JSON', `<pre class="code"><code class="hljs">${esc(JSON.stringify(s.cot, null, 2))}</code></pre>`],
        ],
      });
    });
  }
  function openGT(d) {
    openModal({
      head: `<h3>${esc(pretty(d.experiment))} <span class="badge gt">Ground truth</span></h3><div class="gmeta"><span class="pill">${d.engine}</span><span class="pill">sample #${d.sample_id}</span></div>`,
      video: `videos/hard/${d.experiment}_${d.sample_id}/reference.mp4`,
      tabs: [['Chain-of-thought', renderCoT(d.gt.cot)], ['Parameters', paramRows(d.gt.params, d.gt.cot && d.gt.cot.parameters)], ['Simulation code', codeBlock(d.gt.code)]],
    });
  }
  function openPred(d, m) {
    const md = d.models[m], pe = md.param_eval, gtLaw = (d.gt.cot || {}).physical_law, cot = md.cot;
    const lawCmp = `<div class="cot-sec"><div class="ck">Inferred physical law (${esc(M(m).name)})</div>${renderVal(cot && cot.physical_law, 'physical_law')}</div>
      <div class="cot-sec"><div class="ck">Ground-truth physical law</div>${renderVal(gtLaw, 'physical_law')}</div>
      <div class="cot-sec"><div class="ck">Model's observation</div>${renderVal(cot && cot.physical_observation, 'obs')}</div>`;
    let ptab = '<p class="muted">No parameters could be parsed from this model\'s output.</p>';
    if (pe && !pe.no_record && pe.parse_ok !== false) {
      const matched = pe.matched || [];
      const used = new Set(matched.map(r => r.gt_name));
      const gtp = d.gt.gt_parameters || {};
      const rows = matched.map(r => `<tr class="${r.within_20pct ? 'ok' : ''}"><td><code>${esc(r.gt_name)}</code></td><td class="num">${fmt(r.gt_value)}</td><td><code>${esc(r.pred_name)}</code></td><td class="num">${fmt(r.pred_value)}</td><td class="num">${r.rel_err != null ? (r.rel_err * 100).toFixed(1) + '%' : '—'}</td><td>${r.within_20pct ? '✅' : '❌'}</td></tr>`)
        .concat(Object.entries(gtp).filter(([k]) => !used.has(k)).map(([k, v]) => `<tr class="miss"><td><code>${esc(k)}</code></td><td class="num">${fmt(v && v.value)}</td><td colspan="3">not named by model</td><td>—</td></tr>`));
      const gtN = Object.keys(gtp).length;
      ptab = `<div class="summary-row"><span class="pill ${pe.n_within_tolerance ? 'good' : 'bad'}">${pe.n_within_tolerance}/${gtN} GT params recovered within ±20%</span><span class="pill">${pe.n_matched}/${gtN} named</span><span class="pill">${pe.n_pred_params} predicted in total</span></div>
        <table class="ptable"><thead><tr><th>GT name</th><th>GT value</th><th>Predicted as</th><th>Pred. value</th><th>Rel. err.</th><th>±20%</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
    }
    openModal({
      head: `<h3><span class="mdot" style="background:${M(m).color};width:12px;height:12px"></span>${esc(M(m).name)} <span class="badge ${M(m).group}">${M(m).group}</span></h3><div class="gmeta"><span class="pill">${esc(pretty(d.experiment))}</span><span class="pill">${d.engine}</span><span class="pill">sample #${d.sample_id}</span>${md.completion_tokens ? `<span class="pill">${md.completion_tokens.toLocaleString()} output tokens</span>` : ''}</div>`,
      video: md.video ? `videos/hard/${d.experiment}_${d.sample_id}/${m}.mp4` : null,
      videoNote: md.video ? 'Video rendered by executing the model-generated code.' : 'The generated code did not produce a video (parse, runtime, or truncation failure).',
      tabs: [['Law', lawCmp], ['Parameters vs GT', ptab], ['Generated code', codeBlock(md.code)], ['Full CoT', renderCoT(cot) + (cot && cot.parameters ? `<div class="cot-sec"><div class="ck">parameters</div>${paramRows(null, cot.parameters)}</div>` : '')]],
    });
  }

  // ---------- gallery ----------
  const gstate = { domain: 'all', engine: 'all', q: '', limit: 24 };
  let gallery = [], donut;
  galleryP.then(g => {
    gallery = g;
    const chips = $('#domain-chips');
    const mk = (d, n, c) => h('button', { class: 'chip' + (d === 'all' ? ' active' : ''), 'data-d': d, style: { '--c': c } }, `${esc(d === 'all' ? 'All domains' : d)} <span class="cnt">${n}</span>`);
    chips.append(mk('all', g.length, '#1a1d2e'));
    Object.entries(P.DOMAINS).forEach(([d, v]) => chips.append(mk(d, g.filter(x => x.domain === d).length, v.color)));
    chips.addEventListener('click', e => { const b = e.target.closest('.chip'); if (b) setDomain(b.dataset.d); });
    renderGallery();
  });
  const setDomain = d => {
    gstate.domain = d; gstate.limit = 24;
    $$('#domain-chips .chip').forEach(c => c.classList.toggle('active', c.dataset.d === d));
    if (donut) {
      const keys = Object.keys(P.DOMAINS);
      donut.data.datasets[0].offset = keys.map(k => k === d ? 18 : 0);
      donut.data.datasets[0].backgroundColor = keys.map(k => d === 'all' || k === d ? P.DOMAINS[k].color : alpha(P.DOMAINS[k].color, .25));
      donut.update();
    }
    $('#donut-n').textContent = d === 'all' ? 162 : P.DOMAINS[d].n;
    $('#donut-label').textContent = d === 'all' ? 'experiments' : d;
    renderGallery();
  };
  segHandler('#engine-seg', b => { gstate.engine = b.dataset.e; gstate.limit = 24; renderGallery(); });
  $('#gallery-search').addEventListener('input', e => { gstate.q = e.target.value.trim().toLowerCase(); gstate.limit = 24; renderGallery(); });

  function renderGallery() {
    const items = gallery.filter(x => (gstate.domain === 'all' || x.domain === gstate.domain) && (gstate.engine === 'all' || x.engine === gstate.engine) &&
      (!gstate.q || (x.experiment.replace(/_/g, ' ') + ' ' + x.law + ' ' + x.domain).toLowerCase().includes(gstate.q)));
    const box = $('#gallery'); box.innerHTML = '';
    items.slice(0, gstate.limit).forEach((x, i) => {
      const card = h('div', { class: 'gcard', style: { animationDelay: Math.min(i, 20) * 25 + 'ms' }, onclick: () => openSample(x) });
      const media = h('div', { class: 'gmedia' }, `<img src="videos/posters/${x.experiment}.jpg" alt="${esc(pretty(x.experiment))}" loading="lazy"><span class="eng">${x.engine === 'scipy' ? '2D · SciPy' : '3D · PyBullet'}</span><span class="play">▶</span>`);
      let v;
      const start = () => {
        if (!v) { v = h('video', { muted: '', loop: '', playsinline: '', preload: 'auto' }); v.muted = true; v.src = `videos/gallery/${x.experiment}.mp4`; media.insertBefore(v, media.children[1]); }
        v.play().then(() => card.classList.add('playing')).catch(() => {});
      };
      const stop = () => { if (v) { v.pause(); } card.classList.remove('playing'); };
      card.addEventListener('mouseenter', start); card.addEventListener('mouseleave', stop);
      card.append(media);
      card.append(h('div', { class: 'gbody' }, `<div class="gtitle">${esc(pretty(x.experiment))}</div><div class="glaw">${esc(x.law)}</div><div class="gmeta"><span class="dtag" style="--c:${domColor(x.domain)}">${esc(x.domain)}</span><span class="pill">${x.samples ? x.samples.toLocaleString() + ' samples' : ''}</span></div>`));
      box.append(card);
    });
    if (items.length > gstate.limit) {
      box.append(h('div', { class: 'more-wrap', style: { gridColumn: '1/-1' } }));
      const btn = h('button', { class: 'btn btn-light', onclick: () => { gstate.limit = 999; renderGallery(); } }, `Show all ${items.length} experiments ↓`);
      box.lastChild.append(btn);
    }
    $('#gallery-count').textContent = `Showing ${Math.min(items.length, gstate.limit)} of ${items.length} experiments` + (items.length === 0 ? ' (try clearing filters)' : '');
  }

  lazy('#chart-domains', c => (donut = new Chart(c, {
    type: 'doughnut',
    data: { labels: Object.keys(P.DOMAINS), datasets: [{ data: Object.values(P.DOMAINS).map(v => v.n), backgroundColor: Object.values(P.DOMAINS).map(v => v.color), borderColor: '#fff', borderWidth: 2, hoverOffset: 10, offset: 0 }] },
    options: {
      cutout: '62%', layout: { padding: 14 },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: x => ` ${x.label}: ${x.parsed} experiments (${(x.parsed / 1.62).toFixed(1)}%)` } } },
      onClick: (e, els) => { if (!els.length) return; const d = Object.keys(P.DOMAINS)[els[0].index]; setDomain(gstate.domain === d ? 'all' : d); },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
    },
  })));

  // ---------- construction charts ----------
  lazy('#chart-laws-dist', c => new Chart(c, {
    type: 'bar',
    data: { labels: P.LAWS.map(x => x[0]), datasets: [{ data: P.LAWS.map(x => x[1]), backgroundColor: ['#e8707a', '#ec7f6e', '#f08c3c', '#d9b310', '#74b84a', '#38b2a0', '#4a9be0', '#6d8ae6', '#8c7ae6', '#d66fb0'], borderRadius: 5 }] },
    options: { indexAxis: 'y', scales: { x: { grid, max: 170, title: { display: true, text: 'number of experiments' } }, y: { grid: { display: false } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: x => ` ${x.parsed.x} of 162 experiments` } } } },
  }));
  galleryP.then(g => lazy('#chart-per-exp', c => {
    const s = [...g].sort((a, b) => b.samples - a.samples);
    return new Chart(c, {
      type: 'bar',
      data: { labels: s.map(x => pretty(x.experiment)), datasets: [{ data: s.map(x => x.samples), backgroundColor: s.map(x => domColor(x.domain)), borderRadius: 2, barPercentage: 1, categoryPercentage: .85 }] },
      options: {
        scales: { x: { display: false }, y: { grid, type: 'logarithmic', min: 150, max: 6000, title: { display: true, text: 'samples (log)' }, ticks: { callback: v => [200, 500, 1000, 2000, 5000].includes(v) ? v.toLocaleString() : '' } } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: x => x[0].label, label: x => { const e = s[x.dataIndex]; return [` ${e.samples.toLocaleString()} samples · n_rand = ${e.n_rand}`, ` ${e.domain} · ${e.engine}`, ' click to open']; } } } },
        onClick: (e, els) => { if (els.length) openSample(s[els[0].index]); },
        onHover: (e, els) => { e.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
      },
    });
  }));
  const SCHEMA = [
    ['simulation', 'Experiment-type identifier.', 1], ['category', 'Physics domain (e.g. articulated, rigid-body collision).'],
    ['physical_observation', 'Natural-language description of the visual dynamics, with parameter values.', 1],
    ['physical_law', 'Law name, statement, and governing equation in LaTeX.', 1],
    ['modeling_assumptions', 'Idealisations baked in (point masses, frictionless surfaces, …).'],
    ['ode_system', 'State variables and governing ODE in both LaTeX and Python form.'],
    ['event_schedule', 'Discrete events for collisions / contacts (when applicable).'],
    ['derivation_steps', 'Ordered derivation from first principles to the implemented update.'],
    ['physical_constants', 'Computed quantities (moments of inertia, equilibrium positions, …).'],
    ['numerical_method', 'Solver, tolerances, and closed-form availability.'],
    ['code_validation', 'Analytical checks, limiting behaviours, and plausibility flags.'],
    ['expected_behavior', 'Qualitative predictions about the resulting trajectory.'],
    ['parameters', 'All sampled values with units and human-readable descriptions.', 1],
  ];
  $('#schema-grid').innerHTML = SCHEMA.map(([k, d, req]) => `<div class="schema"><code>${k}</code>${req ? '<span class="req" title="also required in model outputs">model output</span>' : ''}<p>${d}</p></div>`).join('');

  // prior table
  (() => {
    const hd = ['Benchmark', 'Video', 'Text', 'CoT', 'Code', 'Physics laws', 'Engine agnostic', '2D + 3D', '# Exp.', 'Size'];
    $('#prior-table').innerHTML = '<thead><tr>' + hd.map(x => `<th>${x}</th>`).join('') + '</tr></thead><tbody>' +
      P.PRIOR.map(r => `<tr class="${r[0].includes('Ours') ? 'ours' : ''}"><td>${r[0]}</td>` + r.slice(1, 8).map(v => v ? '<td class="y">✓</td>' : '<td class="n">✗</td>').join('') + `<td>${r[8]}</td><td>${r[9]}</td></tr>`).join('') + '</tbody>';
  })();

  // ---------- analysis ----------
  (() => {
    const box = $('#chart-bias').parentElement;
    box.style.height = 'auto';
    let html = `<table class="ptable"><thead><tr><th>Metric</th><th>Claude Sonnet 4.6</th><th>GPT-5 Mini</th></tr></thead><tbody>`;
    for (const [name, c, g, u] of P.T10) {
      const mx = Math.max(Math.abs(c), Math.abs(g), 1e-9);
      const bar = (v, col) => `<div style="display:flex;align-items:center;gap:.5rem"><div style="flex:1;height:10px;background:#f0f1f7;border-radius:99px;position:relative"><span style="position:absolute;top:0;bottom:0;${v >= 0 ? 'left:50%' : 'right:50%'};width:${Math.abs(v) / mx * 50}%;background:${col};border-radius:99px"></span><span style="position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:#aab"></span></div><code style="min-width:62px;text-align:right">${v >= 0 ? '+' : ''}${v.toFixed(name === 'CodeBLEU' ? 3 : 2)}${u ? ' ' + u : ''}</code></div>`;
      html += `<tr><td>${name}</td><td>${bar(c, '#e8590c')}</td><td>${bar(g, '#10a37f')}</td></tr>`;
    }
    html += `<tr><td colspan="3" class="muted" style="font-style:italic">If the benchmark favored Claude: Claude large negative, GPT large positive. Observed: neither.</td></tr></tbody></table>`;
    box.innerHTML = html;
  })();
  lazy('#chart-rho', c => new Chart(c, {
    type: 'bar',
    data: { labels: P.T13.map(x => x[0]), datasets: [{ data: P.T13.map(x => x[1]), backgroundColor: P.T13.map(x => (x[2] === '~0' || +x[2] < .05) ? '#8c7ae6' : '#cfc8f3'), borderRadius: 4 }] },
    options: { indexAxis: 'y', scales: { x: { min: 0, max: 1, grid, title: { display: true, text: "Spearman's ρ (dark: p < 0.05)" } }, y: { grid: { display: false }, ticks: { font: { size: 10.5 } } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: x => ` ρ = ${x.parsed.x.toFixed(3)}, p = ${P.T13[x.dataIndex][2]}` } } } },
  }));
  let framesChart;
  const framesData = k => ({
    datasets: [['qwen', 'Qwen3-VL-30B', '#7048e8'], ['internvl', 'InternVL3.5-30B', '#1c7ed6']].map(([key, label, col]) => ({
      label, borderColor: col, backgroundColor: col, tension: .3, borderWidth: 2.5,
      data: P.T20.frames[key].map((f, i) => ({ x: f, y: P.T20[k][key][i] })),
      pointRadius: P.T20.frames[key].map(f => f === P.T20.paper[key] ? 8 : 4), pointStyle: P.T20.frames[key].map(f => f === P.T20.paper[key] ? 'rectRot' : 'circle'),
    })),
  });
  lazy('#chart-frames', c => (framesChart = new Chart(c, {
    type: 'line', data: framesData('param'),
    options: { scales: { x: { type: 'linear', min: 0, max: 85, grid, title: { display: true, text: 'input frames (◆ = budget used in paper)' } }, y: { grid } } },
  })));
  segHandler('#frames-sub', b => { if (framesChart) { framesChart.data = framesData(b.dataset.k); framesChart.update(); } });

  // ---------- copy buttons ----------
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-copy]'); if (!b) return;
    const t = $(b.dataset.copy); if (!t) return;
    navigator.clipboard.writeText(t.innerText).then(() => { const o = b.textContent; b.textContent = 'Copied ✓'; setTimeout(() => (b.textContent = o), 1400); });
  });
})();
