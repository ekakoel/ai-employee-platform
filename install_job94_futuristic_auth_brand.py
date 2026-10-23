#!/usr/bin/env python3
"""
Job 94 — Brand SVG mark + futuristic auth/onboarding redesign.
Keeps aurora background; flat clear-line inputs; panel transitions;
brand icon tracks cursor gently.

Run from repo root:
  python install_job94_futuristic_auth_brand.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
ASSETS = ROOT / "app" / "static" / "workspace" / "assets"
BRAND_DIR = ROOT / "app" / "static" / "brand"
HTML = ROOT / "app" / "static" / "workspace" / "index.html"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"
JS = ROOT / "app" / "static" / "workspace" / "app.js"

# Prefer artifacts brand if present, else embed
ARTIFACT_SVG = Path("/home/workdir/artifacts/brand/ai-employee-mark.svg")

SVG_CONTENT = r'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" role="img" aria-label="AI Employee Platform">
  <defs>
    <linearGradient id="ring" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#22d3ee"/>
      <stop offset="45%" stop-color="#818cf8"/>
      <stop offset="100%" stop-color="#e879f9"/>
    </linearGradient>
    <linearGradient id="face" x1="50%" y1="0%" x2="50%" y2="100%">
      <stop offset="0%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="#020617"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="45%" r="55%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
      <stop offset="55%" stop-color="#e0f2fe" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="#e0f2fe" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="100" cy="96" r="88" fill="url(#glow)"/>
  <path fill="url(#face)" stroke="url(#ring)" stroke-width="7" stroke-linejoin="round"
        d="M100 28 C145 28 178 55 178 92 C178 122 152 148 118 154 L108 172 C106 176 102 176 100 172 L92 156 C62 148 40 124 40 92 C40 55 55 28 100 28 Z"/>
  <rect x="68" y="78" width="18" height="28" rx="9" fill="#f8fafc"/>
  <rect x="114" y="78" width="18" height="28" rx="9" fill="#f8fafc"/>
  <ellipse cx="100" cy="70" rx="48" ry="18" fill="#ffffff" opacity="0.06"/>
</svg>
'''

FUTURO_CSS = r'''
/* ===== Job 94 — Futuristic auth (aurora kept, no heavy cards) ===== */
.login-gate {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem 1.25rem;
  overflow: hidden;
  background: #070b14;
}
.login-gate::before {
  content: "";
  position: absolute;
  inset: -45%;
  background:
    radial-gradient(ellipse 55% 42% at 18% 28%, rgba(34, 211, 238, 0.28), transparent 58%),
    radial-gradient(ellipse 48% 38% at 82% 18%, rgba(167, 139, 250, 0.30), transparent 52%),
    radial-gradient(ellipse 42% 40% at 62% 82%, rgba(45, 212, 191, 0.18), transparent 52%),
    radial-gradient(ellipse 36% 30% at 28% 72%, rgba(232, 121, 249, 0.12), transparent 50%);
  animation: aurora-drift 20s ease-in-out infinite alternate;
  pointer-events: none;
  z-index: 0;
}
@keyframes aurora-drift {
  0%   { transform: translate3d(-2%, -1%, 0) scale(1); }
  50%  { transform: translate3d(3%, 2%, 0) scale(1.06); }
  100% { transform: translate3d(-1%, 3%, 0) scale(1.02); }
}

.login-shell {
  position: relative;
  z-index: 1;
  width: min(420px, 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.25rem;
}

/* Brand — tracks cursor via --mx/--my */
.brand-orb {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  transform:
    translate3d(calc(var(--mx, 0) * 12px), calc(var(--my, 0) * 10px), 0)
    rotateY(calc(var(--mx, 0) * 14deg))
    rotateX(calc(var(--my, 0) * -12deg));
  transition: transform 0.15s ease-out;
  will-change: transform;
  filter: drop-shadow(0 0 18px rgba(56, 189, 248, 0.35));
}
.brand-orb img,
.brand-orb svg {
  width: 80px;
  height: 80px;
  display: block;
}
.brand-title {
  text-align: center;
  margin: 0;
}
.brand-title h1 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 650;
  letter-spacing: -0.03em;
  background: linear-gradient(120deg, #e2e8f0 0%, #a5f3fc 45%, #c4b5fd 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.brand-title p {
  margin: 0.35rem 0 0;
  color: #94a3b8;
  font-size: 0.85rem;
}

/* Tabs as capsule rail */
.auth-rail {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.35rem;
  width: 100%;
  padding: 0.25rem;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.35);
  border: 1px solid rgba(148, 163, 184, 0.12);
}
.auth-rail .tab {
  border: none;
  background: transparent;
  color: #94a3b8;
  border-radius: 999px;
  padding: 0.4rem 0.85rem;
  font-size: 0.8rem;
  cursor: pointer;
  transition: color 0.2s, background 0.25s, box-shadow 0.25s;
}
.auth-rail .tab.active {
  color: #f8fafc;
  background: rgba(14, 165, 233, 0.18);
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.35);
}

/* Panel transitions */
.auth-stage {
  position: relative;
  width: 100%;
  min-height: 280px;
}
.tab-panel {
  display: none;
  opacity: 0;
  transform: translateY(12px);
  transition: opacity 0.35s ease, transform 0.4s cubic-bezier(0.22, 1, 0.36, 1);
}
.tab-panel.active {
  display: block;
  opacity: 1;
  transform: translateY(0);
  animation: panel-in 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes panel-in {
  from { opacity: 0; transform: translateY(16px) scale(0.985); filter: blur(4px); }
  to   { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
}

/* Clear-line inputs */
.auth-field {
  display: block;
  margin-bottom: 1.1rem;
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
}
.auth-field input,
.login-gate input[type="text"],
.login-gate input[type="email"],
.login-gate input[type="password"],
.login-gate input:not([type]) {
  display: block;
  width: 100%;
  margin-top: 0.4rem;
  padding: 0.7rem 0.15rem 0.55rem;
  font-size: 0.95rem;
  color: #f1f5f9;
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 0;
  outline: none;
  transition: border-color 0.25s, box-shadow 0.25s;
}
.login-gate input:focus {
  border-bottom-color: #22d3ee;
  box-shadow: 0 1px 0 0 rgba(34, 211, 238, 0.55);
}
.password-field {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.28);
}
.password-field input {
  border-bottom: none !important;
  box-shadow: none !important;
  flex: 1;
}
.password-field:focus-within {
  border-bottom-color: #22d3ee;
  box-shadow: 0 1px 0 0 rgba(34, 211, 238, 0.55);
}
.password-toggle {
  background: none;
  border: none;
  color: #64748b;
  font-size: 0.75rem;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* Futuristic primary button */
.btn-futura,
.login-gate .primary.block {
  width: 100%;
  margin-top: 0.75rem;
  padding: 0.8rem 1.2rem;
  border: none;
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.9rem;
  letter-spacing: 0.02em;
  color: #0b1220;
  cursor: pointer;
  background: linear-gradient(120deg, #22d3ee, #818cf8 50%, #e879f9);
  background-size: 160% 100%;
  box-shadow: 0 0 24px rgba(56, 189, 248, 0.25);
  transition: transform 0.2s, filter 0.2s, background-position 0.4s;
}
.btn-futura:hover,
.login-gate .primary.block:hover {
  filter: brightness(1.08);
  background-position: 100% 0;
  transform: translateY(-1px);
}
.login-gate .link-btn {
  color: #7dd3fc;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
}
.login-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 0.5rem 0;
  font-size: 0.8rem;
  color: #94a3b8;
}
.login-message { min-height: 1.25em; font-size: 0.85rem; color: #94a3b8; }
.login-message.error { color: #fca5a5; }

/* Kill old card chrome if still present */
.login-card {
  width: 100%;
  max-width: 420px;
  padding: 0;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  border-radius: 0 !important;
}

/* Onboarding wizard futuristic */
#onboardingWizard {
  background: #070b14;
}
#onboardingWizard::before {
  background:
    radial-gradient(ellipse 50% 40% at 22% 30%, rgba(34, 211, 238, 0.26), transparent 55%),
    radial-gradient(ellipse 42% 36% at 78% 22%, rgba(167, 139, 250, 0.28), transparent 50%),
    radial-gradient(ellipse 40% 40% at 55% 78%, rgba(45, 212, 191, 0.16), transparent 50%);
  animation: aurora-drift 20s ease-in-out infinite alternate;
}
.onboard-card {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  width: min(460px, 94vw);
}
.onboard-steps span.active {
  border-color: rgba(34, 211, 238, 0.5);
  background: rgba(14, 165, 233, 0.12);
  color: #f8fafc;
}
.agent-pick {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.25);
  transition: border-color 0.25s, transform 0.2s, box-shadow 0.25s;
}
.agent-pick:hover, .agent-pick.selected {
  border-color: rgba(34, 211, 238, 0.55);
  box-shadow: 0 0 20px rgba(34, 211, 238, 0.15);
  transform: translateY(-2px);
}
.auth-notice-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 0.75rem;
}
'''


def write_brand_assets() -> str:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    svg = SVG_CONTENT
    if ARTIFACT_SVG.exists():
        svg = ARTIFACT_SVG.read_text(encoding="utf-8")
    target1 = BRAND_DIR / "ai-employee-mark.svg"
    target2 = ASSETS / "brand-mark.svg"
    target1.write_text(svg, encoding="utf-8")
    target2.write_text(svg, encoding="utf-8")
    print(f"[OK] {target1}")
    print(f"[OK] {target2}")
    return "/workspace/assets/brand-mark.svg"


def patch_html(icon_src: str) -> None:
    if not HTML.exists():
        print("[SKIP] index.html")
        return
    t = HTML.read_text(encoding="utf-8")

    # Ensure styles path works — project may use /workspace/styles.css or assets
    if 'href="/workspace/assets/styles.css"' in t and not (ASSETS / "styles.css").exists():
        # keep as-is; styles live at workspace/styles.css served how main configures
        pass

    brand_block = f'''      <div class="login-shell">
      <div class="brand-orb" id="brandOrb" aria-hidden="true">
        <img src="{icon_src}" width="80" height="80" alt="" />
      </div>
      <div class="brand-title login-brand">
        <h1>AI Employee Platform</h1>
        <p id="loginSubtitle">Your intelligent workforce</p>
      </div>
'''
    # Replace old login-brand section opening
    if 'id="brandOrb"' not in t:
        t = t.replace(
            '''    <div class="login-card">
      <div class="login-brand">
        <div class="logo lg">AI</div>
        <div>
          <h1>AI Employee Platform</h1>
          <p id="loginSubtitle">Your workspace</p>
        </div>
      </div>

      <div class="login-tabs">''',
            brand_block + '''
      <div class="login-tabs auth-rail">''',
            1,
        )
        # close login-shell before end of login-card — add before closing of login-card is hard;
        # wrap is enough if shell opens early
    else:
        # update icon src
        t = t.replace(
            'src="/workspace/assets/brand-mark.svg"',
            f'src="{icon_src}"',
        )

    # Tabs class
    t = t.replace('class="login-tabs"', 'class="login-tabs auth-rail"', 1)

    # Wrap panels stage
    if 'class="auth-stage"' not in t:
        t = t.replace(
            '<div id="tab-login" class="tab-panel active">',
            '<div class="auth-stage">\n      <div id="tab-login" class="tab-panel active">',
            1,
        )
        # close stage before end of login-card - find last tab panel area
        # After provision tab is complex; close before </div> of login-card
        if "</div>\n  </div>\n\n  <!--" in t or 'id="workspaceApp"' in t:
            pass

    # Auth notice icon → brand
    if 'id="registerSuccessPanel"' in t and "brand-mark" not in t.split("registerSuccessPanel")[1][:400]:
        t = t.replace(
            '<div class="auth-notice-icon">✉</div>',
            f'<div class="auth-notice-icon"><img src="{icon_src}" width="64" height="64" alt="" /></div>',
            1,
        )

    # Favicon
    if 'rel="icon"' not in t:
        t = t.replace(
            "<title>AI Employee Workspace</title>",
            f'<title>AI Employee Workspace</title>\n  <link rel="icon" type="image/svg+xml" href="{icon_src}" />',
            1,
        )

    HTML.write_text(t, encoding="utf-8")
    print("[OK] index.html brand + shell")


def patch_css() -> None:
    if not CSS.exists():
        CSS.write_text(FUTURO_CSS, encoding="utf-8")
        print("[OK] styles.css created")
        return
    t = CSS.read_text(encoding="utf-8")
    if "Job 94 — Futuristic auth" in t:
        # replace block
        start = t.find("/* ===== Job 94")
        if start >= 0:
            t = t[:start] + FUTURO_CSS
        else:
            t = t + "\n" + FUTURO_CSS
    else:
        t = t.rstrip() + "\n\n" + FUTURO_CSS
    CSS.write_text(t, encoding="utf-8")
    # Also copy to assets if index links there
    if 'href="/workspace/assets/styles.css"' in (HTML.read_text(encoding="utf-8") if HTML.exists() else ""):
        ASSETS.mkdir(parents=True, exist_ok=True)
        shutil.copy(CSS, ASSETS / "styles.css")
        print("[OK] assets/styles.css synced")
    print("[OK] styles.css futuristic")


def patch_js() -> None:
    if not JS.exists():
        print("[SKIP] app.js")
        return
    t = JS.read_text(encoding="utf-8")
    cursor_js = r'''
  // Job 94 — brand orb follows pointer (subtle)
  (function bindBrandOrb() {
    const gate = document.getElementById("loginGate");
    const orb = document.getElementById("brandOrb");
    if (!gate || !orb) return;
    let raf = 0;
    let tx = 0, ty = 0, cx = 0, cy = 0;
    function tick() {
      cx += (tx - cx) * 0.12;
      cy += (ty - cy) * 0.12;
      gate.style.setProperty("--mx", cx.toFixed(4));
      gate.style.setProperty("--my", cy.toFixed(4));
      raf = requestAnimationFrame(tick);
    }
    gate.addEventListener("pointermove", (e) => {
      const r = gate.getBoundingClientRect();
      tx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      ty = ((e.clientY - r.top) / r.height - 0.5) * 2;
      tx = Math.max(-1, Math.min(1, tx));
      ty = Math.max(-1, Math.min(1, ty));
    });
    gate.addEventListener("pointerleave", () => { tx = 0; ty = 0; });
    raf = requestAnimationFrame(tick);
  })();

  // Job 94 — smoother tab panel transitions
  document.querySelectorAll(".login-tabs .tab, .auth-rail .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.getAttribute("data-tab");
      if (!name) return;
      document.querySelectorAll(".tab-panel").forEach((p) => {
        if (p.classList.contains("active")) {
          p.classList.remove("active");
        }
      });
      // re-trigger animation
      requestAnimationFrame(() => {
        const panel = document.getElementById("tab-" + name) || document.getElementById(name);
        // registerSuccessPanel special
        const target = document.getElementById("tab-" + name);
        if (target) {
          void target.offsetWidth;
          target.classList.add("active");
        }
      });
    });
  });
'''
    if "bindBrandOrb" not in t:
        # insert near end of IIFE or after DOM ready login handlers
        if '$("btnLogin").onclick' in t:
            t = t.replace(
                '$("btnLogin").onclick = async () => {',
                cursor_js + '\n  $("btnLogin").onclick = async () => {',
                1,
            )
        else:
            t = t + "\n" + cursor_js
    JS.write_text(t, encoding="utf-8")
    print("[OK] app.js cursor + transitions")


def main() -> int:
    print("Job 94 — Futuristic auth + brand mark")
    print(f"ROOT: {ROOT}")
    if not (ROOT / "app").is_dir():
        raise SystemExit("run from repo root")
    icon = write_brand_assets()
    patch_html(icon)
    patch_css()
    patch_js()
    print(
        f"""
Brand icon: {icon}
Also: app/static/brand/ai-employee-mark.svg

Next:
  # Restart server if needed; Ctrl+F5 /workspace
  git add app/static/brand/ai-employee-mark.svg \\
          app/static/workspace/assets/brand-mark.svg \\
          app/static/workspace/index.html \\
          app/static/workspace/styles.css \\
          app/static/workspace/assets/styles.css \\
          app/static/workspace/app.js
  git commit -m "Job 94: brand mark SVG, futuristic auth UI, cursor orb, panel transitions"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
