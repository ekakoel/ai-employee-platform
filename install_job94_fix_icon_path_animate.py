#!/usr/bin/env python3
"""
Job 94 FIX — brand icon 404 + blink/expression animation.

Root cause: main.py mounts StaticFiles(directory=workspace/) at /workspace/assets
so URL /workspace/assets/brand-mark.svg → file workspace/brand-mark.svg
NOT workspace/assets/brand-mark.svg.

Also inlines animated SVG into #brandOrb (no network 404) and adds blink CSS.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
WS = ROOT / "app" / "static" / "workspace"
HTML = WS / "index.html"
CSS = WS / "styles.css"
JS = WS / "app.js"

# Animated brand: blink lids + soft look, gradient ring
ANIM_SVG = r'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" class="brand-svg" role="img" aria-label="AI Employee">
  <defs>
    <linearGradient id="ae-ring" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#22d3ee"/>
      <stop offset="45%" stop-color="#818cf8"/>
      <stop offset="100%" stop-color="#e879f9"/>
    </linearGradient>
    <linearGradient id="ae-face" x1="50%" y1="0%" x2="50%" y2="100%">
      <stop offset="0%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="#020617"/>
    </linearGradient>
    <radialGradient id="ae-glow" cx="50%" cy="45%" r="55%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9"/>
      <stop offset="60%" stop-color="#e0f2fe" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="#e0f2fe" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle class="ae-halo" cx="100" cy="96" r="88" fill="url(#ae-glow)"/>
  <path fill="url(#ae-face)" stroke="url(#ae-ring)" stroke-width="7" stroke-linejoin="round"
        d="M100 28 C145 28 178 55 178 92 C178 122 152 148 118 154 L108 172 C106 176 102 176 100 172 L92 156 C62 148 40 124 40 92 C40 55 55 28 100 28 Z"/>
  <!-- eyes group: pupils track via CSS vars; lids blink -->
  <g class="ae-eyes" transform="translate(0,0)">
    <g class="ae-eye ae-eye-l" transform="translate(77,92)">
      <rect class="ae-white" x="-9" y="-14" width="18" height="28" rx="9" fill="#f8fafc"/>
      <circle class="ae-pupil" cx="0" cy="2" r="4.5" fill="#0f172a"/>
      <rect class="ae-lid" x="-10" y="-15" width="20" height="30" rx="10" fill="#0b1220"/>
    </g>
    <g class="ae-eye ae-eye-r" transform="translate(123,92)">
      <rect class="ae-white" x="-9" y="-14" width="18" height="28" rx="9" fill="#f8fafc"/>
      <circle class="ae-pupil" cx="0" cy="2" r="4.5" fill="#0f172a"/>
      <rect class="ae-lid" x="-10" y="-15" width="20" height="30" rx="10" fill="#0b1220"/>
    </g>
  </g>
  <ellipse cx="100" cy="70" rx="48" ry="18" fill="#ffffff" opacity="0.06"/>
</svg>'''

ANIM_CSS = r'''
/* Job 94 fix — animated brand face */
.brand-orb {
  width: 92px;
  height: 92px;
  display: grid;
  place-items: center;
}
.brand-orb .brand-svg {
  width: 84px;
  height: 84px;
  display: block;
  overflow: visible;
}
.brand-orb .ae-halo {
  animation: ae-pulse 3.2s ease-in-out infinite;
  transform-origin: 100px 96px;
}
@keyframes ae-pulse {
  0%, 100% { opacity: 0.85; }
  50% { opacity: 1; }
}
/* lids start open (scaleY 0), blink shut */
.brand-orb .ae-lid {
  transform-box: fill-box;
  transform-origin: center top;
  transform: scaleY(0);
  animation: ae-blink 4.2s ease-in-out infinite;
}
.brand-orb .ae-eye-r .ae-lid {
  animation-delay: 0.08s;
}
@keyframes ae-blink {
  0%, 42%, 50%, 100% { transform: scaleY(0); }
  45%, 47% { transform: scaleY(1); }
}
/* pupils look around */
.brand-orb .ae-pupil {
  animation: ae-look 5.5s ease-in-out infinite;
}
.brand-orb .ae-eye-r .ae-pupil {
  animation-delay: 0.05s;
}
@keyframes ae-look {
  0%, 100% { transform: translate(0, 0); }
  20% { transform: translate(2px, 1px); }
  40% { transform: translate(-2px, 0); }
  60% { transform: translate(1px, -1px); }
  80% { transform: translate(-1px, 1px); }
}
/* happy squint on hover */
.brand-orb:hover .ae-lid {
  animation: none;
  transform: scaleY(0.35);
  transform-origin: center bottom;
}
.brand-orb:hover .ae-pupil {
  animation: none;
  transform: translate(0, 3px);
}
'''


def write_svg_files() -> None:
    WS.mkdir(parents=True, exist_ok=True)
    # Correct path for mount: /workspace/assets/X → workspace/X
    path = WS / "brand-mark.svg"
    # Static file version (simpler, still has basic SMIL-less CSS hooks via classes)
    path.write_text(ANIM_SVG, encoding="utf-8")
    print(f"[OK] {path}  → URL /workspace/assets/brand-mark.svg")
    # Also keep nested copy for people who open folder assets/
    nested = WS / "assets"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "brand-mark.svg").write_text(ANIM_SVG, encoding="utf-8")
    print(f"[OK] {nested / 'brand-mark.svg'} (duplicate)")


def patch_html_inline() -> None:
    if not HTML.exists():
        print("[SKIP] index.html")
        return
    t = HTML.read_text(encoding="utf-8")
    # Replace img brand with inline animated SVG
    t2 = re.sub(
        r'<div class="brand-orb" id="brandOrb"[^>]*>[\s\S]*?</div>',
        '<div class="brand-orb" id="brandOrb" aria-hidden="true">\n'
        + ANIM_SVG
        + "\n      </div>",
        t,
        count=1,
    )
    # Favicon still file URL (correct path)
    t2 = t2.replace(
        'href="/workspace/assets/assets/brand-mark.svg"',
        'href="/workspace/assets/brand-mark.svg"',
    )
    # Any img src pointing to wrong nested path
    t2 = t2.replace(
        'src="/workspace/assets/assets/brand-mark.svg"',
        'src="/workspace/assets/brand-mark.svg"',
    )
    HTML.write_text(t2, encoding="utf-8")
    print("[OK] index.html inline animated SVG in #brandOrb")


def patch_css() -> None:
    if not CSS.exists():
        print("[SKIP] styles.css")
        return
    t = CSS.read_text(encoding="utf-8")
    if "ae-blink" in t:
        # refresh block
        if "Job 94 fix — animated brand face" in t:
            start = t.find("/* Job 94 fix — animated brand face */")
            t = t[:start] + ANIM_CSS
        else:
            t = t.rstrip() + "\n" + ANIM_CSS
    else:
        t = t.rstrip() + "\n\n" + ANIM_CSS
    CSS.write_text(t, encoding="utf-8")
    print("[OK] styles.css blink/look animations")


def patch_js_expression() -> None:
    """Pupils also follow cursor slightly when orb is present."""
    if not JS.exists():
        return
    t = JS.read_text(encoding="utf-8")
    snippet = r'''
  // Job 94 fix — pupils follow pointer inside brand orb
  (function brandPupils() {
    const orb = document.getElementById("brandOrb");
    if (!orb) return;
    const pupils = orb.querySelectorAll(".ae-pupil");
    if (!pupils.length) return;
    window.addEventListener("pointermove", (e) => {
      const r = orb.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      let dx = (e.clientX - cx) / (r.width / 2);
      let dy = (e.clientY - cy) / (r.height / 2);
      dx = Math.max(-1, Math.min(1, dx)) * 2.5;
      dy = Math.max(-1, Math.min(1, dy)) * 2;
      pupils.forEach((p) => {
        p.style.animation = "none";
        p.setAttribute("transform", `translate(${dx}, ${dy})`);
      });
    });
  })();
'''
    if "brandPupils" not in t:
        if "bindBrandOrb" in t:
            t = t.replace(
                "(function bindBrandOrb()",
                snippet + "\n  (function bindBrandOrb()",
                1,
            )
        elif '$("btnLogin")' in t:
            t = t.replace(
                '$("btnLogin").onclick',
                snippet + "\n  $(\"btnLogin\").onclick",
                1,
            )
        else:
            t = t + "\n" + snippet
        JS.write_text(t, encoding="utf-8")
        print("[OK] app.js pupil tracking")
    else:
        print("[OK] app.js pupil tracking already")


def main() -> int:
    print("Job 94 FIX — icon path + blink expression")
    print(f"ROOT: {ROOT}")
    if not WS.is_dir():
        raise SystemExit("workspace static missing — run from repo root")
    write_svg_files()
    patch_html_inline()
    patch_css()
    patch_js_expression()
    print(
        """
URL yang benar:
  /workspace/assets/brand-mark.svg  →  app/static/workspace/brand-mark.svg

Icon login memakai SVG inline (kedip + lihat + ikuti kursor).

  # Restart server optional; Ctrl+F5
  git add app/static/workspace/brand-mark.svg \\
          app/static/workspace/assets/brand-mark.svg \\
          app/static/workspace/index.html \\
          app/static/workspace/styles.css \\
          app/static/workspace/app.js
  git commit -m "Job 94 fix: brand icon path, blink/expression animation"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
