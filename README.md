# Crash Dashboard (Web-First)

This project now runs as a browser-first crash dashboard.

The web app can:

- Run live ArcGIS crash queries directly from the browser
- Render map markers with severity filters
- Show summary cards, severity breakdown, and recent crash table
- Fall back to `output.json` when needed

## Web Flow (Primary)

Host the dashboard locally:

```bash
python -m http.server 8000
```

Open:

`http://localhost:8000/index.html`

Then in the page:

1. Set your ArcGIS `/query` endpoint and filters.
2. Click **Run Live Query**.
3. Use **Load output.json** only when you want to view static saved data.

## Optional Python CLI (Data Export)

If you still want to export GeoJSON from CLI, use `crash_parser.py`:

Run a query against the feature layer `/query` endpoint:

```bash
python crash_parser.py "https://REPLACE_WITH_ACTUAL_ENDPOINT_URL/query"
```

The default point and date filter match the example in the prompt:

```bash
python crash_parser.py "https://REPLACE_WITH_ACTUAL_ENDPOINT_URL/query" \
  --longitude -76.1775 \
  --latitude 36.7806 \
  --start-date 2020-01-01 \
  --distance 1
```

Save the returned GeoJSON to a file:

```bash
python crash_parser.py "https://REPLACE_WITH_ACTUAL_ENDPOINT_URL/query" --json-out crash_geojson.json
```

The desktop Tkinter UI remains in the repo for compatibility but is no longer the primary workflow.

## Unit tests

Run the unit tests:

```bash
python -m unittest discover -s tests -v
```

## GitHub Pages Dashboard

This repository includes a static dashboard in `index.html` that can be hosted on GitHub Pages.

To use it on GitHub Pages:

1. Commit `index.html`, `styles.css`, and `app.js` to your repository.
2. Optionally commit `output.json` if you want static fallback data.
3. In GitHub, go to Settings > Pages.
4. Set the source to the root of the main branch.
5. Open the Pages URL after GitHub finishes building the site.

To test locally before publishing:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/index.html` in your browser.
