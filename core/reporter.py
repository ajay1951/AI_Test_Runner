"""
HTML and JSON Test Execution Report Generator.
Features credential masking, dedicated assertion breakdowns, and interactive step timelines.
"""

import os
import re
import json
import time
from datetime import datetime
from jinja2 import Template
from typing import List, Dict, Any, Optional

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Test Report - {{ title }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; margin: 0; line-height: 1.5; }
    .container { max-width: 980px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 24px; }
    .badge { padding: 6px 16px; border-radius: 9999px; font-weight: bold; text-transform: uppercase; font-size: 0.9rem; }
    .badge-pass { background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .badge-fail { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    .stat-card { background: #1e293b; padding: 16px; border-radius: 8px; border: 1px solid #334155; text-align: center; }
    .stat-num { font-size: 1.8rem; font-weight: bold; margin-top: 4px; }
    .step { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px; }
    .step-header { display: flex; justify-content: space-between; align-items: center; }
    .action-tag { background: #334155; color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-family: monospace; }
    .assertion-box { background: rgba(16, 185, 129, 0.1); border-left: 4px solid #10b981; padding: 8px 12px; border-radius: 4px; margin-top: 8px; font-size: 0.85rem; color: #a7f3d0; }
    .error-box { background: rgba(239, 68, 68, 0.15); border-left: 4px solid #ef4444; padding: 8px 12px; border-radius: 4px; margin-top: 8px; font-size: 0.85rem; color: #fca5a5; font-family: monospace; }
    .screenshot { max-width: 100%; border-radius: 6px; margin-top: 12px; border: 1px solid #475569; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1 style="font-size: 1.6rem; margin: 0 0 4px 0;">AI Test Automation Report</h1>
        <div style="color: #94a3b8; font-size: 0.85rem;">Scenario: {{ title }} | Executed at: {{ timestamp }}</div>
      </div>
      <div class="badge {% if passed %}badge-pass{% else %}badge-fail{% endif %}">
        {% if passed %}PASSED{% else %}FAILED{% endif %}
      </div>
    </div>

    <div class="stats">
      <div class="stat-card">
        <div style="color: #94a3b8; font-size: 0.8rem;">TOTAL ACTIONS</div>
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

    <h2 style="font-size: 1.2rem; margin-bottom: 14px;">Execution Timeline</h2>
    {% for s in steps %}
    <div class="step">
      <div class="step-header">
        <div>
          <span class="action-tag">{{ s.action }}</span>
          <strong style="margin-left: 8px; font-size: 0.95rem;">Step {{ loop.index }}: {{ s.instruction }}</strong>
        </div>
        <span style="font-size: 0.8rem; font-weight: bold; color: {% if s.success %}#10b981{% else %}#ef4444{% endif %};">
          {% if s.success %}PASSED{% else %}FAILED{% endif %} ({{ s.duration_ms }}ms)
        </span>
      </div>

      {% if s.rationale %}
      <div style="color: #64748b; font-size: 0.8rem; margin-top: 4px;">{{ s.rationale }}</div>
      {% endif %}

      {% if s.assertion_result %}
      <div class="assertion-box">
        ✓ Verified {{ s.assertion_result.type }}: {{ s.assertion_result.get('expected') or s.assertion_result.get('target') }}
      </div>
      {% endif %}

      {% if s.error %}
      <div class="error-box">
        ❌ {{ s.error }}
      </div>
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

        # Sanitize sensitive data in reports
        sanitized_steps = []
        for s in steps_data:
            s_copy = dict(s)
            for k in ["instruction", "rationale", "error"]:
                val = str(s_copy.get(k) or "")
                if val:
                    # Mask any cleartext password tokens
                    masked = re.sub(r'(password\s+)([^\s,;]+)', r'\1********', val, flags=re.IGNORECASE)
                    masked = re.sub(r'(fill with\s+)([^\s,;]+)', r'\1********', masked, flags=re.IGNORECASE)
                    masked = re.sub(r'(\bsecret\w*|\bdemouser\b|\bdemoadmin\b)', '********', masked, flags=re.IGNORECASE)
                    s_copy[k] = masked
            sanitized_steps.append(s_copy)

        data = {
            "title": title,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "passed": passed,
            "duration_sec": duration_sec,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "steps": sanitized_steps
        }

        # Save JSON Report
        json_path = os.path.join(self.output_dir, f"report_{timestamp_str}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Save HTML Report
        html_path = os.path.join(self.output_dir, f"report_{timestamp_str}.html")
        tmpl = Template(HTML_TEMPLATE)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(tmpl.render(**data))

        return html_path
