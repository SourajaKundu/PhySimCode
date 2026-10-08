# PhySimCode — project page

Project website for **PhySimCode: A Benchmark and Evaluation Method for Physics Video to Code Generation**.

Live at: https://sourajakundu.github.io/PhySimCode/

## Updating links
Paper (arXiv) and code links are set at the top of `assets/js/main.js`:

```js
const LINKS = { paper: '', code: '' };
```

Fill in the URLs and the buttons enable automatically. Update the BibTeX block in `index.html` once the arXiv ID is available.

## Layout
- `index.html`, `assets/` — page, styles, scripts (`assets/js/paperdata.js` holds all numbers transcribed from the paper)
- `data/gallery.json`, `data/samples/` — one sample per experiment (162) with CoT, parameters and code
- `data/hard.json`, `data/hard/` — the 10 hard samples with every model's predictions and parameter matching
- `videos/` — web-encoded (H.264) dataset and regenerated videos

## Results presentation

The main benchmark shows five core metrics in a sortable table. Secondary metrics and evaluation details are expandable. A separate table reports all fourteen models on the ten hard samples; these scores must not be compared directly with the main evaluation set. All table values come from `assets/js/paperdata.js`.

The page uses a solid ivory, ink, and teal palette, with dataset images in the hero. There is no chart dependency. Tables support keyboard sorting and retain the model column while scrolling on small screens. The demo shows a static completed example when reduced motion is enabled.

## Local preview

Serve this directory with `python -m http.server 8000`, then open `http://localhost:8000`. No build step is required.
