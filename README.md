# Crash Query Tool

This app queries a VDOT / local crash feature layer and returns the matching crash records as GeoJSON.

## Command line

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

## Desktop UI

Launch the desktop app:

```bash
python crash_ui.py
```

In the UI you can:

- Enter the query endpoint URL
- Set longitude, latitude, start date, and radius
- Override the WHERE clause if needed
- View the record count and query parameters
- Save the GeoJSON response as JSON

## Unit tests

Run the unit tests:

```bash
python -m unittest discover -s tests -v
```

## GitHub Pages Dashboard

This repository now includes a static dashboard in `index.html` that reads `output.json` and can be hosted on GitHub Pages.

To use it on GitHub Pages:

1. Commit `index.html`, `styles.css`, `app.js`, and `output.json` to your repository.
2. In GitHub, go to Settings > Pages.
3. Set the source to the root of the main branch.
4. Open the Pages URL after GitHub finishes building the site.

To test locally before publishing:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/index.html` in your browser.
