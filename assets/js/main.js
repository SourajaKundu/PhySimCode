/* PhySimCode project page */
(() => {
  // Fill these in when available; the buttons enable themselves automatically.
  const LINKS = { paper: '', code: '' };

  const P = window.PAPER;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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
  document.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[role="button"]')) { e.preventDefault(); e.target.click(); }
  });
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
  const logoTag = (id, cls = 'mlogo') => M(id).logo ? `<img class="${cls}" src="${M(id).logo}" alt="" loading="lazy">` : `<span class="mdot" style="background:${M(id).color}"></span>`;
  // ---------- links ----------
  for (const [k, url] of Object.entries(LINKS)) {
    const b = $('#btn-' + k);
    if (b && url) { b.href = url; b.target = '_blank'; b.classList.remove('disabled'); b.removeAttribute('aria-disabled'); b.removeAttribute('tabindex'); b.rel = 'noopener'; b.querySelector('small')?.remove(); }
    else b?.addEventListener('click', e => e.preventDefault());
  }

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
  const navToggle = $('.nav-toggle');
  const closeNav = () => { document.body.classList.remove('nav-open'); navToggle.setAttribute('aria-expanded', 'false'); navToggle.setAttribute('aria-label', 'Open menu'); };
  navToggle.addEventListener('click', () => {
    const open = document.body.classList.toggle('nav-open');
    navToggle.setAttribute('aria-expanded', String(open));
    navToggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeNav(); });
  const secIO = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id));
  }), { rootMargin: '-45% 0px -50% 0px' });
  navLinks.forEach(a => { const s = $(a.getAttribute('href')); s && secIO.observe(s); a.addEventListener('click', closeNav); });

  // ---------- autoplay only when visible ----------
  const vidIO = new IntersectionObserver(es => es.forEach(e => {
    const v = e.target;
    if (e.isIntersecting) { if (!reducedMotion && v.dataset.paused !== '1') v.play().catch(() => {}); }
    else v.pause();
  }), { rootMargin: '100px' });
  const autoVideo = (src, cls) => {
    const v = h('video', { muted: '', loop: '', playsinline: '', preload: 'metadata', class: cls || '' });
    v.muted = true; v.src = src; vidIO.observe(v); return v;
  };

  // ---------- data ----------
  const galleryP = getJSON('data/gallery.json');
  const hardP = getJSON('data/hard.json');

  // ---------- animated demo ----------
  const demoP = getJSON('data/demo.json');
  const hl = (text, lang) => { try { return hljs.highlight(text, { language: lang }).value; } catch { return esc(text); } };
  Promise.all([demoP, galleryP]).then(([d, g]) => initDemo(d, g));

  function initDemo(D, gallery) {
    const stage = $('#demo-stage'), cap = $('#demo-caption');
    const dpIn = $('#dp-in'), dpMid = $('#dp-mid'), dpOut = $('#dp-out');
    const vIn = $('#demo-in'), vGen = $('#demo-gen'), genWrap = $('.gen-wrap', dpOut);
    const edCot = $('#ed-cot code'), edCode = $('#ed-code code'), edTerm = $('#ed-term');
    const mllm = $('#mllm'), score = $('#scorecard'), flyers = $('#flyer-layer');
    const pe = D.param_eval, gtNames = Object.keys(D.gt_params || {});
    const okSet = new Set((pe.matched || []).filter(m => m.within_20pct).map(m => m.gt_name));
    const avg = a => a.reduce((x, y) => x + y, 0) / a.length;
    const lawEq = avg(D.scores.law_equivalence);
    const pc = D.pred_cot || {};
    const slimParams = Object.fromEntries(Object.entries(pc.parameters || {}).map(([k, v]) => [k, v && typeof v === 'object' ? `${v.value}${v.unit ? ' ' + v.unit : ''}` : v]));
    const cotText = JSON.stringify({ simulation: pc.simulation, physical_law: pc.physical_law, parameters: slimParams }, null, 2);
    const codeText = D.pred_code || '';
    const termText = `$ python simulation.py\n  integrating dynamics (6 balls, walls, restitution) …\n  rendering frames → video.mp4 …\n✓ done in ${(3.1).toFixed(1)} s · video.mp4 written`;
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
      const t0 = vt; let lastN = -1, lastDraw = -1e9;
      const f = () => {
        if (id !== runId) { frameFns.delete(f); return reject(CANCEL); }
        const n = Math.min(text.length, Math.floor(text.length * (vt - t0) / ms));
        if (n !== lastN && (n >= text.length || vt - lastDraw >= 33)) {
          lastDraw = vt;
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
      return row('Physical law', `${lawEq.toFixed(1)} / 5`, `<div class="sc-bar"><span data-w="${lawEq / 5 * 100}" style="background:#6ec9b6"></span></div><div class="sc-note">3 LLM judges: does it match the law in the video?</div>`) +
        row('Parameters within ±20%', `${ok} / ${gtNames.length}`, `<div class="sc-params">${chips}</div>`) +
        row('Video similarity', `${D.scores.dino.toFixed(2)} · ${D.scores.xclip.toFixed(2)}`, `<div class="sc-bar"><span data-w="${D.scores.dino * 100}" style="background:#e6b46c"></span></div><div class="sc-note">DINOv2 · VideoCLIP cosine vs. the input</div>`) +
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
    const STEPS = [
      { dur: 4200, cap: 'Input: just a video', sub: '',
        run: async (inst, id) => { focus(dpIn); dpMid.classList.add('hide'); dpOut.classList.add('hide'); if (!inst) { restartVideos(); } } },
      { dur: 3600, cap: 'The MLLM watches the frames', sub: '',
        run: async (inst, id) => { dpMid.classList.remove('hide'); dpOut.classList.remove('hide'); dpOut.classList.add('dim'); focus(dpMid); mllm.classList.add('busy'); setTab('cot'); if (!inst) fly(); } },
      { dur: 4300, cap: 'It infers the physics', sub: 'the governing law and every parameter value, as JSON',
        run: async (inst, id) => { setTab('cot'); if (inst) edCot.innerHTML = hl(cotText, 'json'); else await typeInto(edCot, cotText, 3000, 'json', id); } },
      { dur: 6000, cap: 'It writes the simulation from scratch', sub: 'self-contained Python: NumPy, SciPy, Matplotlib',
        run: async (inst, id) => { setTab('code'); if (inst) edCode.innerHTML = hl(codeText, 'python'); else await typeInto(edCode, codeText, 5000, 'python', id); } },
      { dur: 4600, cap: 'We run the code', sub: 'it renders a brand-new video',
        run: async (inst, id) => {
          setTab('term'); mllm.classList.remove('busy');
          if (inst) edTerm.textContent = termText; else await typeInto(edTerm, termText, 1600, null, id);
          dpOut.classList.remove('dim'); focus(dpOut); genWrap.classList.add('on'); if (!inst) restartVideos();
        } },
      { dur: 6200, cap: 'We score it against the input', sub: 'law · parameters · video · code',
        run: async (inst, id) => { focus(dpOut); await showCards(inst, id); } },
    ];
    const bars = $('#demo-steps');
    STEPS.forEach((s, i) => { const b = h('button', { class: 'dstep', style: { '--w': s.dur }, title: s.cap, 'aria-label': `Step ${i + 1}: ${s.cap}` }, '<span></span>'); b.onclick = () => go(i); bars.append(b); });

    const reset = () => {
      waiters.clear(); frameFns.clear(); flyers.innerHTML = '';
      [dpIn, dpMid, dpOut].forEach(x => x.classList.remove('dim', 'focus', 'hide'));
      mllm.classList.remove('busy'); setTab('cot');
      edCot.innerHTML = ''; edCode.innerHTML = ''; edTerm.textContent = '';
      genWrap.classList.remove('on'); score.innerHTML = '';
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
      $('#demo-pause').setAttribute('aria-label', p ? 'Pause demo' : 'Play demo');
      [vIn, vGen].forEach(v => (p && inView ? v.play().catch(() => {}) : v.pause()));
    }
    $('#demo-pause').onclick = () => { if (!started || cur >= STEPS.length) { started = true; userPaused = false; return go(0); } setPlaying(!playing); userPaused = !playing; };
    $('#demo-replay').onclick = () => { started = true; userPaused = false; go(0); };
    let userPaused = reducedMotion;
    if (reducedMotion) { reset(); STEPS.forEach(s => s.run(true, runId)); cur = STEPS.length; started = true; setCaption(STEPS.length - 1); setPlaying(false); }
    new IntersectionObserver(es => es.forEach(e => {
      inView = e.isIntersecting;
      if (inView && !started && !reducedMotion) { started = true; go(0); }
      else if (started && cur < STEPS.length && !userPaused) setPlaying(inView);
    }), { threshold: 0.35 }).observe($('#demo'));
    requestAnimationFrame(loop);
  }

  // ---------- result tables ----------
  // Keep all displayed values sourced from paperdata.js. A solid highlight marks
  // the best value; there is no heatmap or cross-metric aggregate ranking.
  const MAIN = P.MAIN;
  const column = (label, unit, value, digits = 2, suffix = '') => ({ label, unit, value, digits, suffix });
  const modelColumn = column('Model', '', m => M(m).name);
  function resultTable(selector, ids, columns, defaultSort, caption) {
    const table = $(selector);
    let sort = defaultSort, ascending = false;
    const best = columns.map((c, i) => i ? Math.max(...ids.map(c.value)) : null);
    const render = () => {
      const sorted = [...ids].sort((a, b) => {
        const x = columns[sort].value(a), y = columns[sort].value(b);
        const comparison = typeof x === 'string' ? x.localeCompare(y) : x - y;
        return comparison * (ascending ? 1 : -1);
      });
      table.innerHTML = `<caption class="sr-only">${esc(caption)}</caption><thead><tr>` + columns.map((c, i) =>
        `<th scope="col" aria-sort="${i === sort ? (ascending ? 'ascending' : 'descending') : 'none'}"><button type="button" data-sort="${i}">${esc(c.label)}<span class="sort-arrow" aria-hidden="true">${i === sort ? (ascending ? '↑' : '↓') : '↕'}</span>${c.unit ? `<small>${esc(c.unit)}</small>` : ''}</button></th>`
      ).join('') + '</tr></thead><tbody>' + sorted.map(id => '<tr>' + columns.map((c, i) => {
        if (!i) return `<th scope="row">${logoTag(id)}<span class="model-name">${esc(M(id).name)}<small>${({ frontier: 'Frontier', closed: 'Closed-source', open: 'Open-source' })[M(id).group]}</small></span></th>`;
        const v = c.value(id), text = v.toFixed(c.digits) + c.suffix;
        return `<td${v === best[i] ? ' class="best"' : ''}>${v === best[i] ? `<strong>${text}</strong><span class="sr-only"> (best)</span>` : text}</td>`;
      }).join('') + '</tr>').join('') + '</tbody>';
    };
    table.addEventListener('click', e => {
      const button = e.target.closest('[data-sort]');
      if (!button) return;
      const next = +button.dataset.sort;
      ascending = sort === next ? !ascending : next === 0;
      sort = next;
      render();
      table.querySelector(`[data-sort="${sort}"]`).focus({ preventScroll: true });
    });
    render();
  }
  resultTable('#full-table', MAIN, [modelColumn,
    column('Law validity', '1–5 · LLM judges', m => P.T3[m][1]),
    column('Law match', '1–5 · LLM judges', m => P.T3[m][5]),
    column('Physics match', '1–5 · human raters', m => P.T4[m][1]),
    column('Parameters recovered', 'within ±20%', m => P.T5[m][0], 2, '%'),
    column('Code runs', 'without errors', m => P.T5[m][4], 1, '%'),
  ], 3, 'Main benchmark: ten models on 2,430 videos. Higher is better.');
  resultTable('#extra-table', MAIN, [modelColumn,
    column('Plausibility', '1–5 · human raters', m => P.T4[m][0]),
    column('Appearance match', '1–5 · human raters', m => P.T4[m][2]),
    column('DINOv2', 'cosine similarity', m => P.T4[m][3], 3),
    column('VideoCLIP', 'cosine similarity', m => P.T4[m][4], 3),
    column('Parameters named', 'ground-truth recall', m => P.T9[m][3] * 100, 1, '%'),
    column('Video saved', 'share of inputs', m => P.T5[m][5], 1, '%'),
    column('CodeBLEU', 'code similarity', m => P.T5[m][6], 3),
  ], 1, 'Additional metrics on the main benchmark. Higher is better.');
  resultTable('#frontier-table', [...P.FRONTIER, ...MAIN], [modelColumn,
    column('Law match', '1–5 · LLM judges', m => P.T6[m][5]),
    column('Parameters recovered', 'within ±20%', m => P.T8[m][0], 2, '%'),
    column('DINOv2', 'cosine similarity', m => P.T7[m][0], 3),
    column('VideoCLIP', 'cosine similarity', m => P.T7[m][1], 3),
  ], 1, 'Separate evaluation: fourteen models on ten hand-picked hard samples. Higher is better.');

  // ---------- comparator ----------
  const cmp = { detail: null, playing: !reducedMotion, speed: 1 };
  $('#cmp-play').textContent = cmp.playing ? '❚❚ Pause all' : '▶ Play all';
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
      const t = h('div', { class: 'sthumb', role: 'button', tabindex: '0', 'aria-label': `Compare ${pretty(s.experiment)}`, onclick: () => selectHard(s, t) },
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
          const tile = h('div', { class: 'tile', role: 'button', tabindex: '0', 'aria-label': `View ${M(m).name} prediction`, style: { '--c': M(m).color }, onclick: () => openPred(d, m) });
          if (md.video) tile.append(autoVideo(`videos/hard/${s.tag}/${m}.mp4`));
          else tile.append(h('div', { class: 'failed' }, `<div>✕ Failed<small>no video produced</small></div>`));
          tile.append(h('div', { class: 'tile-label' }, `${logoTag(m)}${esc(M(m).name)}`));
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
  let modalTrigger = null;
  const closeModal = () => { if (!modal.classList.contains('open')) return; modal.classList.remove('open'); modal.setAttribute('aria-hidden', 'true'); modalTrigger?.focus(); $('#modal-media').innerHTML = ''; document.body.style.overflow = ''; };
  modal.addEventListener('click', e => { if (e.target.closest('[data-close]')) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
  modal.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const controls = $$('button, a[href], input, select, video[controls], [tabindex="0"]', modal).filter(el => el.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  const openModal = ({ head, video, videoNote, tabs }) => {
    modalTrigger = document.activeElement;
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
    modal.classList.add('open'); modal.setAttribute('aria-hidden', 'false'); $('.modal-close').focus(); document.body.style.overflow = 'hidden';
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
      head: `<h3>${logoTag(m, 'mlogo lg')}${esc(M(m).name)} <span class="badge ${M(m).group}">${M(m).group}</span></h3><div class="gmeta"><span class="pill">${esc(pretty(d.experiment))}</span><span class="pill">${d.engine}</span><span class="pill">sample #${d.sample_id}</span>${md.completion_tokens ? `<span class="pill">${md.completion_tokens.toLocaleString()} output tokens</span>` : ''}</div>`,
      video: md.video ? `videos/hard/${d.experiment}_${d.sample_id}/${m}.mp4` : null,
      videoNote: md.video ? 'Video rendered by executing the model-generated code.' : 'The generated code did not produce a video (parse, runtime, or truncation failure).',
      tabs: [['Law', lawCmp], ['Parameters vs GT', ptab], ['Generated code', codeBlock(md.code)], ['Full CoT', renderCoT(cot) + (cot && cot.parameters ? `<div class="cot-sec"><div class="ck">parameters</div>${paramRows(null, cot.parameters)}</div>` : '')]],
    });
  }

  // ---------- gallery ----------
  const gstate = { domain: 'all', engine: 'all', q: '', limit: 24 };
  let gallery = [];
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
    renderGallery();
  };
  segHandler('#engine-seg', b => { gstate.engine = b.dataset.e; gstate.limit = 24; renderGallery(); });
  $('#gallery-search').addEventListener('input', e => { gstate.q = e.target.value.trim().toLowerCase(); gstate.limit = 24; renderGallery(); });

  function renderGallery() {
    const items = gallery.filter(x => (gstate.domain === 'all' || x.domain === gstate.domain) && (gstate.engine === 'all' || x.engine === gstate.engine) &&
      (!gstate.q || (x.experiment.replace(/_/g, ' ') + ' ' + x.law + ' ' + x.domain).toLowerCase().includes(gstate.q)));
    const box = $('#gallery'); box.innerHTML = '';
    items.slice(0, gstate.limit).forEach((x, i) => {
      const card = h('div', { class: 'gcard', role: 'button', tabindex: '0', 'aria-label': `Open ${pretty(x.experiment)}`, style: { animationDelay: Math.min(i, 20) * 25 + 'ms' }, onclick: () => openSample(x) });
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

  // ---------- copy buttons ----------
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-copy]'); if (!b) return;
    const t = $(b.dataset.copy); if (!t) return;
    navigator.clipboard.writeText(t.innerText).then(() => { const o = b.textContent; b.textContent = 'Copied ✓'; setTimeout(() => (b.textContent = o), 1400); });
  });
})();
