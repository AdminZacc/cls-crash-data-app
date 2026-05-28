import json
import tkinter as tk
from collections import Counter
from datetime import datetime
import tempfile
import webbrowser
from html import escape
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Optional

from crash_parser import (
    DEFAULT_DISTANCE_MILES,
    DEFAULT_LATITUDE,
    DEFAULT_LONGITUDE,
    DEFAULT_WHERE,
    fetch_crash_geojson,
)


DEFAULT_API_URL = "https://services.arcgis.com/p5v98VHDX9Atv3l7/arcgis/rest/services/Full_Crash/FeatureServer/0/query"
SEVERITY_ORDER = ["K", "A", "B", "C", "O", "Unknown"]
AWS_NAVY = "#232f3e"
AWS_BLUE = "#0972d3"
AWS_ORANGE = "#ff9900"
AWS_BG = "#f7f9fb"
AWS_CARD = "#ffffff"
AWS_TEXT = "#1b2533"
AWS_MUTED = "#5f6b7a"
AWS_BORDER = "#d7dde5"
MAP_SEVERITY_COLORS = {
    "K": "#7f1d1d",
    "A": "#b91c1c",
    "B": "#d97706",
    "C": "#0369a1",
    "O": "#6b7280",
    "Unknown": "#6b7280",
}


def _safe_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_crash_dt(value: object) -> str:
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(float(value) / 1000.0).strftime("%Y-%m-%d %H:%M")
    return "Unknown"


def build_dashboard_data(summary: dict) -> dict[str, object]:
    features = summary.get("geojson", {}).get("features", [])

    severity_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    rows: list[dict[str, object]] = []
    total_injured = 0.0
    total_killed = 0.0
    total_vehicles = 0.0
    earliest_dt: Optional[datetime] = None
    latest_dt: Optional[datetime] = None

    for feature in features:
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        crash_dt_value = properties.get("CRASH_DT")
        crash_dt = None
        if isinstance(crash_dt_value, (int, float)):
            crash_dt = datetime.utcfromtimestamp(float(crash_dt_value) / 1000.0)
            if earliest_dt is None or crash_dt < earliest_dt:
                earliest_dt = crash_dt
            if latest_dt is None or crash_dt > latest_dt:
                latest_dt = crash_dt

        severity_value = str(properties.get("CRASH_SEVERITY") or "Unknown").strip().upper()
        if severity_value not in SEVERITY_ORDER:
            severity_value = severity_value[:1] if severity_value else "Unknown"
        if severity_value not in SEVERITY_ORDER:
            severity_value = "Unknown"
        severity_counts[severity_value] += 1

        route_value = str(properties.get("ROUTE_OR_STREET_NM") or "Unknown").strip() or "Unknown"
        route_counts[route_value] += 1

        injured_value = _safe_float(properties.get("PERSONS_INJURED"))
        killed_value = _safe_float(properties.get("K_PEOPLE"))
        vehicle_value = _safe_float(properties.get("VEH_COUNT"))
        total_injured += injured_value
        total_killed += killed_value
        total_vehicles += vehicle_value

        rows.append(
            {
                "dt_sort": crash_dt_value if isinstance(crash_dt_value, (int, float)) else 0,
                "date": _format_crash_dt(crash_dt_value),
                "severity": severity_value,
                "injured": int(injured_value),
                "killed": int(killed_value),
                "vehicles": int(vehicle_value),
                "route": route_value,
                "jurisdiction": str(properties.get("PHYSICAL_JURIS") or "Unknown"),
                "document": str(properties.get("DOCUMENT_NBR") or "Unknown"),
                "lat": properties.get("LAT"),
                "lon": properties.get("LON"),
            }
        )

    rows.sort(key=lambda row: row["dt_sort"], reverse=True)
    top_route = route_counts.most_common(1)[0] if route_counts else ("Unknown", 0)

    return {
        "records": len(features),
        "start_date": summary.get("start_date"),
        "end_date": summary.get("end_date"),
        "date_range": {
            "start": earliest_dt.strftime("%Y-%m-%d %H:%M") if earliest_dt else "Unknown",
            "end": latest_dt.strftime("%Y-%m-%d %H:%M") if latest_dt else "Unknown",
        },
        "total_injured": int(total_injured),
        "total_killed": int(total_killed),
        "average_vehicles": round(total_vehicles / len(features), 2) if features else 0.0,
        "severity_counts": {key: severity_counts.get(key, 0) for key in SEVERITY_ORDER if severity_counts.get(key, 0) > 0},
        "top_route": {"name": top_route[0], "count": top_route[1]},
        "recent_rows": rows[:20],
    }


class CrashParserUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Crash Query Tool")
        self.geometry("1240x860")
        self.minsize(1040, 720)
        self.configure(bg=AWS_BG)

        self._configure_styles()

        self.api_url_var = tk.StringVar(value=DEFAULT_API_URL)
        self.longitude_var = tk.StringVar(value=str(DEFAULT_LONGITUDE))
        self.latitude_var = tk.StringVar(value=str(DEFAULT_LATITUDE))
        self.start_date_var = tk.StringVar(value="2020-01-01")
        self.end_date_var = tk.StringVar(value="")
        self.distance_var = tk.DoubleVar(value=float(DEFAULT_DISTANCE_MILES))
        self.distance_display_var = tk.StringVar(value=f"{float(DEFAULT_DISTANCE_MILES):.1f} mi")
        self.where_var = tk.StringVar(value="")
        self.timeout_var = tk.StringVar(value="30")
        self.json_out_var = tk.StringVar()
        self.last_summary: Optional[dict] = None

        self._build_layout()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Dashboard.TFrame", background=AWS_BG)
        style.configure("Header.TFrame", background=AWS_NAVY)
        style.configure("HeaderTitle.TLabel", background=AWS_NAVY, foreground="white", font=("Segoe UI", 20, "bold"))
        style.configure("HeaderSub.TLabel", background=AWS_NAVY, foreground="#d3d7de", font=("Segoe UI", 10))

        style.configure("Section.TLabelframe", background=AWS_BG, borderwidth=0)
        style.configure("Section.TLabelframe.Label", background=AWS_BG, foreground=AWS_TEXT, font=("Segoe UI", 11, "bold"))

        style.configure("Treeview", background="white", foreground=AWS_TEXT, fieldbackground="white", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=AWS_NAVY, foreground="white", font=("Segoe UI", 10, "bold"))
        style.map("Treeview.Heading", background=[("active", AWS_BLUE)])
        style.map("Treeview", background=[("selected", AWS_ORANGE)], foreground=[("selected", "#111111")])

    def _build_layout(self) -> None:
        root = tk.Frame(self, padx=16, pady=16, bg=AWS_BG)
        root.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(root, bg=AWS_NAVY, padx=18, pady=16)
        header.pack(fill=tk.X)
        tk.Label(header, text="Virginia Crash Dashboard", bg=AWS_NAVY, fg="white", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="ArcGIS-powered crash analytics with live query controls and dashboard cards.",
            bg=AWS_NAVY,
            fg="#d3d7de",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        file_frame = ttk.LabelFrame(root, text="Crash Query", style="Section.TLabelframe", padding=12)
        file_frame.pack(fill=tk.X)

        tk.Label(file_frame, text="API endpoint:").grid(row=0, column=0, sticky="w")
        tk.Entry(file_frame, textvariable=self.api_url_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        file_frame.columnconfigure(1, weight=1)

        filter_frame = ttk.LabelFrame(root, text="Filters", style="Section.TLabelframe", padding=12)
        filter_frame.pack(fill=tk.X, pady=(10, 0))

        tk.Label(filter_frame, text="Longitude:").grid(row=0, column=0, sticky="w")
        tk.Entry(filter_frame, textvariable=self.longitude_var, width=12).grid(
            row=0, column=1, sticky="w", padx=(8, 16)
        )

        tk.Label(filter_frame, text="Latitude:").grid(row=0, column=2, sticky="w")
        tk.Entry(filter_frame, textvariable=self.latitude_var, width=12).grid(
            row=0, column=3, sticky="w", padx=(8, 0)
        )

        tk.Label(filter_frame, text="Start date:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        tk.Entry(filter_frame, textvariable=self.start_date_var, width=16).grid(
            row=1, column=1, sticky="w", padx=(8, 16), pady=(10, 0)
        )

        tk.Label(filter_frame, text="End date:").grid(row=1, column=2, sticky="w", pady=(10, 0))
        tk.Entry(filter_frame, textvariable=self.end_date_var, width=16).grid(
            row=1, column=3, sticky="w", padx=(8, 0), pady=(10, 0)
        )

        tk.Label(filter_frame, text="Distance (miles):").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        distance_container = tk.Frame(filter_frame, bg=AWS_BG)
        distance_container.grid(row=2, column=1, sticky="ew", padx=(8, 16), pady=(10, 0))
        tk.Scale(
            distance_container,
            from_=0.5,
            to=50.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            variable=self.distance_var,
            command=self._on_distance_slider,
            length=220,
            bg=AWS_BG,
            highlightthickness=0,
            troughcolor="#dbe5f0",
            activebackground=AWS_ORANGE,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            distance_container,
            textvariable=self.distance_display_var,
            bg=AWS_BG,
            fg=AWS_MUTED,
            width=8,
            anchor="w",
        ).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(filter_frame, text="WHERE clause (optional):").grid(
            row=2, column=2, sticky="w", pady=(10, 0)
        )
        tk.Entry(filter_frame, textvariable=self.where_var).grid(
            row=2, column=3, sticky="ew", padx=(8, 0), pady=(10, 0)
        )
        filter_frame.columnconfigure(1, weight=1)
        filter_frame.columnconfigure(3, weight=1)

        tk.Label(
            filter_frame,
            text="Tip: leave End date blank for an open-ended search; the end date is inclusive.",
            fg="#555555",
            wraplength=760,
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))

        output_frame = ttk.LabelFrame(root, text="Output", style="Section.TLabelframe", padding=12)
        output_frame.pack(fill=tk.X, pady=(10, 0))

        tk.Label(output_frame, text="JSON output file (optional):").grid(row=0, column=0, sticky="w")
        tk.Entry(output_frame, textvariable=self.json_out_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        tk.Button(output_frame, text="Browse", command=self._browse_json_output).grid(
            row=0, column=2
        )
        output_frame.columnconfigure(1, weight=1)

        button_frame = tk.Frame(root)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        tk.Button(button_frame, text="Run Query", command=self._run_query).pack(side=tk.LEFT)
        tk.Button(button_frame, text="Open Map", command=self._open_map).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(button_frame, text="Save JSON", command=self._save_json).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(button_frame, text="Clear", command=self._clear_output).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        dashboard_frame = ttk.LabelFrame(root, text="Dashboard", style="Section.TLabelframe", padding=12)
        dashboard_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self._build_dashboard(dashboard_frame)

        result_frame = ttk.LabelFrame(root, text="Query Log", style="Section.TLabelframe", padding=12)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.output_text = ScrolledText(result_frame, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True)

    def _build_dashboard(self, parent: ttk.LabelFrame) -> None:
        self.kpi_vars = {
            "records": tk.StringVar(value="0"),
            "date_range": tk.StringVar(value="Unknown"),
            "injured": tk.StringVar(value="0"),
            "killed": tk.StringVar(value="0"),
            "vehicles": tk.StringVar(value="0.00"),
            "route": tk.StringVar(value="Unknown"),
        }

        cards_frame = ttk.Frame(parent)
        cards_frame.pack(fill=tk.X)
        card_specs = [
            ("Records", "records"),
            ("Date Range", "date_range"),
            ("People Injured", "injured"),
            ("People Killed", "killed"),
            ("Avg Vehicles", "vehicles"),
            ("Top Route", "route"),
        ]
        for index, (label_text, key) in enumerate(card_specs):
            card = tk.Frame(cards_frame, bg=AWS_CARD, bd=1, relief="solid", highlightthickness=0, padx=12, pady=10)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))
            tk.Label(card, textvariable=self.kpi_vars[key], bg=AWS_CARD, fg=AWS_TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w")
            tk.Label(card, text=label_text, bg=AWS_CARD, fg=AWS_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))
            cards_frame.columnconfigure(index, weight=1)

        middle_frame = ttk.Frame(parent)
        middle_frame.pack(fill=tk.X, pady=(12, 0))

        severity_frame = ttk.LabelFrame(middle_frame, text="Severity Breakdown", style="Section.TLabelframe", padding=10)
        severity_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.severity_value_vars: dict[str, tk.StringVar] = {}
        for index, key in enumerate(SEVERITY_ORDER):
            value_var = tk.StringVar(value="0")
            self.severity_value_vars[key] = value_var
            row = tk.Frame(severity_frame, bg=AWS_BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=key, width=10, bg=AWS_BG, fg=AWS_TEXT, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
            tk.Label(row, textvariable=value_var, bg=AWS_BG, fg=AWS_BLUE, font=("Segoe UI", 10)).pack(side=tk.LEFT)

        route_frame = ttk.LabelFrame(middle_frame, text="Top Route", style="Section.TLabelframe", padding=10)
        route_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        self.top_route_var = tk.StringVar(value="Unknown")
        tk.Label(route_frame, textvariable=self.top_route_var, wraplength=280, justify="left", bg=AWS_BG, fg=AWS_TEXT, font=("Segoe UI", 10)).pack(anchor="w")

        table_frame = ttk.LabelFrame(parent, text="Recent Crashes", style="Section.TLabelframe", padding=10)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        columns = ("date", "severity", "injured", "killed", "vehicles", "route", "jurisdiction")
        self.crash_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        self.crash_tree.heading("date", text="Date")
        self.crash_tree.heading("severity", text="Severity")
        self.crash_tree.heading("injured", text="Injured")
        self.crash_tree.heading("killed", text="Killed")
        self.crash_tree.heading("vehicles", text="Vehicles")
        self.crash_tree.heading("route", text="Route")
        self.crash_tree.heading("jurisdiction", text="Jurisdiction")

        self.crash_tree.column("date", width=150, anchor="w")
        self.crash_tree.column("severity", width=80, anchor="center")
        self.crash_tree.column("injured", width=80, anchor="center")
        self.crash_tree.column("killed", width=80, anchor="center")
        self.crash_tree.column("vehicles", width=80, anchor="center")
        self.crash_tree.column("route", width=340, anchor="w")
        self.crash_tree.column("jurisdiction", width=120, anchor="w")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.crash_tree.yview)
        self.crash_tree.configure(yscrollcommand=y_scroll.set)
        self.crash_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _clear_dashboard(self) -> None:
        for key, var in self.kpi_vars.items():
            if key == "vehicles":
                var.set("0.00")
            elif key == "date_range":
                var.set("Unknown")
            elif key == "route":
                var.set("Unknown")
            else:
                var.set("0")
        for var in self.severity_value_vars.values():
            var.set("0")
        self.top_route_var.set("Unknown")
        if hasattr(self, "crash_tree"):
            for item in self.crash_tree.get_children():
                self.crash_tree.delete(item)

    def _browse_json_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save GeoJSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.json_out_var.set(path)

    def _on_distance_slider(self, value: str) -> None:
        try:
            self.distance_display_var.set(f"{float(value):.1f} mi")
        except (TypeError, ValueError):
            self.distance_display_var.set("0.0 mi")

    def _collect_query_values(self) -> dict[str, object]:
        api_url = self.api_url_var.get().strip()
        if not api_url:
            raise ValueError("Please enter a crash query endpoint URL.")

        longitude_value = self.longitude_var.get().strip()
        latitude_value = self.latitude_var.get().strip()
        start_date = self.start_date_var.get().strip() or "2020-01-01"
        distance = float(self.distance_var.get())
        where_clause = self.where_var.get().strip() or None
        timeout_value = self.timeout_var.get().strip() or "30"

        try:
            longitude = float(longitude_value)
            latitude = float(latitude_value)
            timeout = float(timeout_value)
        except ValueError as exc:
            raise ValueError("Longitude, latitude, and timeout must be numeric.") from exc

        return {
            "api_url": api_url,
            "longitude": longitude,
            "latitude": latitude,
            "start_date": start_date,
            "end_date": self.end_date_var.get().strip() or None,
            "distance_miles": distance,
            "where_clause": where_clause,
            "timeout": timeout,
        }

    def _run_query(self) -> None:
        try:
            query_values = self._collect_query_values()
        except Exception as exc:
            messagebox.showerror("Invalid Input", str(exc))
            return

        try:
            summary = fetch_crash_geojson(
                query_values["api_url"],
                longitude=query_values["longitude"],
                latitude=query_values["latitude"],
                start_date=query_values["start_date"],
                end_date=query_values["end_date"],
                distance_miles=query_values["distance_miles"],
                where_clause=query_values["where_clause"],
                timeout=float(query_values["timeout"]),
            )
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return

        self.last_summary = summary
        self._render_dashboard(summary)
        self._render_summary(summary)

        json_path = self.json_out_var.get().strip()
        if json_path:
            try:
                Path(json_path).write_text(json.dumps(summary["geojson"], indent=2), encoding="utf-8")
            except Exception as exc:
                messagebox.showerror("JSON Save Error", str(exc))

    def _save_json(self) -> None:
        if not self.last_summary:
            messagebox.showinfo("No Result", "Run a query first.")
            return

        output_path = self.json_out_var.get().strip()
        if not output_path:
            output_path = filedialog.asksaveasfilename(
                title="Save summary JSON",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not output_path:
                return
            self.json_out_var.set(output_path)

        try:
            Path(output_path).write_text(json.dumps(self.last_summary["geojson"], indent=2), encoding="utf-8")
            messagebox.showinfo("Saved", f"Summary saved to:\n{output_path}")
        except Exception as exc:
            messagebox.showerror("Save Failed", str(exc))

    def _clear_output(self) -> None:
        self.output_text.delete("1.0", tk.END)
        self.last_summary = None
        self._clear_dashboard()

        def _open_map(self) -> None:
                if not self.last_summary:
                        messagebox.showinfo("No Result", "Run a query first.")
                        return

                map_rows: list[dict[str, object]] = []
            features = self.last_summary.get("geojson", {}).get("features", [])
            for feature in features:
                properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
                severity_value = str(properties.get("CRASH_SEVERITY") or "Unknown").strip().upper()
                if severity_value not in SEVERITY_ORDER:
                    severity_value = severity_value[:1] if severity_value else "Unknown"
                if severity_value not in SEVERITY_ORDER:
                    severity_value = "Unknown"

                row = {
                    "date": _format_crash_dt(properties.get("CRASH_DT")),
                    "severity": severity_value,
                    "injured": int(_safe_float(properties.get("PERSONS_INJURED"))),
                    "killed": int(_safe_float(properties.get("K_PEOPLE"))),
                    "route": str(properties.get("ROUTE_OR_STREET_NM") or "Unknown"),
                    "jurisdiction": str(properties.get("PHYSICAL_JURIS") or "Unknown"),
                    "lat": properties.get("LAT"),
                    "lon": properties.get("LON"),
                }

                        # Filter out rows that cannot be placed on the map.
                        lat = row.get("lat")
                        lon = row.get("lon")
                        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                                continue
                        map_rows.append(row)

                if not map_rows:
                        messagebox.showinfo("No Map Data", "No coordinates are available to plot.")
                        return

                html_text = self._build_map_html(map_rows)
                map_path = Path(tempfile.gettempdir()) / "crash_dashboard_map.html"
                map_path.write_text(html_text, encoding="utf-8")
                webbrowser.open(map_path.as_uri())

        def _build_map_html(self, rows: list[dict[str, object]]) -> str:
                marker_rows: list[dict[str, object]] = []
                for row in rows:
                        severity = str(row.get("severity") or "Unknown")
                        marker_rows.append(
                                {
                                        "lat": float(row["lat"]),
                                        "lon": float(row["lon"]),
                                        "severity": severity,
                                        "color": MAP_SEVERITY_COLORS.get(severity, MAP_SEVERITY_COLORS["Unknown"]),
                                        "popup": (
                                                f"<strong>{escape(str(row.get('route') or 'Unknown'))}</strong><br/>"
                                                f"Severity: {escape(severity)}<br/>"
                                                f"Injured: {int(row.get('injured') or 0)} | Killed: {int(row.get('killed') or 0)}<br/>"
                                                f"Date: {escape(str(row.get('date') or 'Unknown'))}<br/>"
                                                f"Jurisdiction: {escape(str(row.get('jurisdiction') or 'Unknown'))}"
                                        ),
                                }
                        )

                markers_json = json.dumps(marker_rows)
                severity_json = json.dumps(SEVERITY_ORDER)

                return f"""<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"UTF-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
        <title>Crash Map</title>
        <link
            rel=\"stylesheet\"
            href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"
            integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\"
            crossorigin=\"\"
        />
        <style>
            html, body {{
                height: 100%;
                margin: 0;
                font-family: Segoe UI, Arial, sans-serif;
                background: #f7f9fb;
            }}
            .shell {{
                display: flex;
                flex-direction: column;
                height: 100%;
            }}
            .toolbar {{
                padding: 10px 12px;
                border-bottom: 1px solid #d7dde5;
                background: #ffffff;
            }}
            .toolbar-title {{
                font-size: 14px;
                font-weight: 600;
                color: #1b2533;
                margin-bottom: 8px;
            }}
            .chips {{
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }}
            .chip {{
                border: 1px solid #c4ccd7;
                background: #ffffff;
                color: #1b2533;
                border-radius: 999px;
                padding: 4px 10px;
                cursor: pointer;
            }}
            .chip.active {{
                background: #0972d3;
                border-color: #0972d3;
                color: white;
            }}
            #map {{
                flex: 1;
                min-height: 320px;
            }}
        </style>
    </head>
    <body>
        <div class=\"shell\">
            <div class=\"toolbar\">
                <div class=\"toolbar-title\">Crash Locations</div>
                <div id=\"chips\" class=\"chips\"></div>
            </div>
            <div id=\"map\"></div>
        </div>

        <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\" crossorigin=\"\"></script>
        <script>
            const markers = {markers_json};
            const severityOrder = {severity_json};
            const selectedSeverities = new Set(severityOrder);

            const map = L.map("map", {{ zoomControl: true, scrollWheelZoom: true }}).setView([36.7806, -76.1775], 11);
            L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                maxZoom: 19,
            }}).addTo(map);

            const markerLayer = L.layerGroup().addTo(map);
            const chipsEl = document.getElementById("chips");

            function renderMarkers() {{
                markerLayer.clearLayers();
                const bounds = [];

                for (const row of markers) {{
                    if (!selectedSeverities.has(row.severity)) continue;
                    const latLng = [row.lat, row.lon];
                    bounds.push(latLng);
                    const marker = L.circleMarker(latLng, {{
                        radius: 6,
                        color: row.color,
                        weight: 2,
                        fillColor: row.color,
                        fillOpacity: 0.82,
                    }});
                    marker.bindPopup(row.popup);
                    marker.addTo(markerLayer);
                }}

                if (bounds.length > 0) {{
                    map.fitBounds(bounds, {{ padding: [20, 20] }});
                }}
            }}

            function renderChips() {{
                chipsEl.innerHTML = "";
                for (const severity of severityOrder) {{
                    const count = markers.filter((row) => row.severity === severity).length;
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "chip" + (selectedSeverities.has(severity) ? " active" : "");
                    button.textContent = `${{severity}} (${{count}})`;
                    button.addEventListener("click", () => {{
                        if (selectedSeverities.has(severity) && selectedSeverities.size === 1) return;
                        if (selectedSeverities.has(severity)) selectedSeverities.delete(severity);
                        else selectedSeverities.add(severity);
                        renderChips();
                        renderMarkers();
                    }});
                    chipsEl.appendChild(button);
                }}
            }}

            renderChips();
            renderMarkers();
        </script>
    </body>
</html>
"""

    def _render_dashboard(self, summary: dict) -> None:
        dashboard = build_dashboard_data(summary)

        self.kpi_vars["records"].set(str(dashboard["records"]))
        self.kpi_vars["date_range"].set(f"{dashboard['date_range']['start']} -> {dashboard['date_range']['end']}")
        self.kpi_vars["injured"].set(str(dashboard["total_injured"]))
        self.kpi_vars["killed"].set(str(dashboard["total_killed"]))
        self.kpi_vars["vehicles"].set(f"{dashboard['average_vehicles']:.2f}")
        self.kpi_vars["route"].set(f"{dashboard['top_route']['name']} ({dashboard['top_route']['count']})")
        self.top_route_var.set(f"{dashboard['top_route']['name']}\n{dashboard['top_route']['count']} crashes")

        for key in SEVERITY_ORDER:
            if key in self.severity_value_vars:
                self.severity_value_vars[key].set(str(dashboard["severity_counts"].get(key, 0)))

        for item in self.crash_tree.get_children():
            self.crash_tree.delete(item)

        for row in dashboard["recent_rows"]:
            self.crash_tree.insert(
                "",
                tk.END,
                values=(
                    row["date"],
                    row["severity"],
                    row["injured"],
                    row["killed"],
                    row["vehicles"],
                    row["route"],
                    row["jurisdiction"],
                ),
            )

    def _render_summary(self, summary: dict) -> None:
        self.output_text.delete("1.0", tk.END)

        lines: list[str] = []
        lines.append("=== Crash Query Result ===")
        lines.append(f"Endpoint: {summary['api_url']}")
        lines.append(f"Location: ({summary['latitude']}, {summary['longitude']})")
        lines.append(f"Distance: {summary['distance_miles']} mile(s)")
        lines.append(f"Start date: {summary['start_date']}")
        if summary.get("end_date"):
            lines.append(f"End date: {summary['end_date']}")
        lines.append(f"Where: {summary['where']}")
        lines.append(f"Successfully retrieved {summary['feature_count']} crash records.")
        lines.append("")
        lines.append("Query parameters:")
        lines.append(json.dumps(summary["query_params"], indent=2))

        self.output_text.insert(tk.END, "\n".join(lines))


def main() -> None:
    app = CrashParserUI()
    app.mainloop()


if __name__ == "__main__":
    main()
