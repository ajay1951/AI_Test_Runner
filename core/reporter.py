"""
HTML and JSON Test Execution Report Generator.
"""

import os
import json
import time
from datetime import datetime
from jinja2 import Template
from typing import List, Dict, Any, Optional

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Test Execution Report - {{ title }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; margin: 0; }
    .container { max-width: 950px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 24px; }
    .badge { padding: 6px 16px; border-radius: 9999px; font-weight: bold; text-transform: uppercase; font-size: 0.9rem; }
    .badge-pass { background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .badge-fail { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    .stat-card { background: #1e293b; padding: 16px; border-radius: 8px; border: 1px solid #334155; text-align: center; }
    .stat-num { font-size: 1.8rem; font-weight: bold; margin-top: 4px; }
    .step { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px; }
    .step-header { display: flex; justify-content: space-between; align-items: center; }
    .screenshot { max-width: 100%; border-radius: 6px; margin-top: 12px; border: 1px solid #475569; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1 style="font-size: 1.5rem; margin: 0 0 4px 0;">AI Test Execution Report</h1>
        <div style="color: #94a3b8; font-size: 0.85rem;">Test: {{ title }} | Executed at: {{ timestamp }}</div>
      </div>
      <div class="badge {% if passed %}badge-pass{% else %}badge-fail{% endif %}">
        {% if passed %}PASSED{% else %}FAILED{% endif %}
      </div>
    </div>

    <div class="stats">
      <div class="stat-card">
        <div style="color: #94a3b8; font-size: 0.8rem;">TOTAL STEPS</div>
        <div class="stat-num">{{ steps|length }}</div>
      </div>
      <div class="stat-card">
        <div style="color: #94a3b8; font-size: 0.8rem;">SUCCESSFUL</div>
        <div class="stat-num" style="color: #10b981;">{{ passed_count }}</div>
      </div>
      <div class="stat-card">
        <div style="color: #94a3b8; font-size: 0.8rem;">FAILED</div>
        <div class="stat-num" style="color: {% if failed_count > 0 %}#ef4444{% else %}#94a3b8{% endif %};">{{ failed_count }}</div>
      </div>
      <div class="stat-card">
        <div style="color: #94a3b8; font-size: 0.8rem;">DURATION</div>
        <div class="stat-num">{{ duration_sec }}s</div>
      </div>
    </div>

    <h2 style="font-size: 1.15rem; margin-bottom: 14px;">Execution Timeline</h2>
    {% for s in steps %}
    <div class="step">
      <div class="step-header">
        <div>
          <span style="background: #334155; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-family: monospace;">{{ s.action }}</span>
          <strong style="margin-left: 8px; font-size: 0.95rem;">Step {{ loop.index }}: {{ s.instruction }}</strong>
        </div>
        <span style="font-size: 0.8rem; font-weight: bold; color: {% if s.success %}#10b981{% else %}#ef4444{% endif %};">
          {% if s.success %}PASSED{% else %}FAILED{% endif %}
        </span>
      </div>
      {% if s.rationale %}
      <div style="color: #64748b; font-size: 0.8rem; margin-top: 4px;">{{ s.rationale }}</div>
      {% endif %}
      {% if s.screenshot %}
      <img class="screenshot" src="{{ s.screenshot }}" alt="Step screenshot">
      {% endif %}
    </div>
    {% endfor %}
  </div>
</body>
</html>
"""


class TestReporter:
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, title: str, steps_data: List[Dict[str, Any]], passed: bool, duration_ms: float) -> str:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        passed_count = sum(1 for s in steps_data if s.get("success", False))
        failed_count = len(steps_data) - passed_count
        duration_sec = round(duration_ms / 1000.0, 2)

        data = {
            "title": title,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "passed": passed,
            "duration_sec": duration_sec,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "steps": steps_data
        }

        # Save JSON
        json_path = os.path.join(self.output_dir, f"report_{timestamp_str}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Save HTML
        html_path = os.path.join(self.output_dir, f"report_{timestamp_str}.html")
        tmpl = Template(HTML_TEMPLATE)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(tmpl.render(**data))

        return html_path

