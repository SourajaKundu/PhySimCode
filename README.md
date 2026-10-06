# PhySimCode — project page

Project website for **PhySimCode: A Benchmark and Evaluation Method for Physics Video to Code Generation**.

Live at: https://sourajakundu.github.io/PhySImCode/

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
