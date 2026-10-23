#!/usr/bin/env python3
"""Job 95 fix — kill white autofill, remove icon glow, natural blink."""
from pathlib import Path

ROOT = Path.cwd()
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"
JS = ROOT / "app" / "static" / "workspace" / "app.js"

CSS_BLOCK = r'''
/* Job 95 fix2 — autofill + icon polish */
.login-gate input,
.login-gate input[type="text"],
.login-gate input[type="email"],
.login-gate input[type="password"],
.login-gate textarea,
#onboardingWizard input {
  background-color: transparent !important;
  color: #f1f5f9 !important;
  -webkit-text-fill-color: #f1f5f9 !important;
  caret-color: #22d3ee;
}

/* Chromium/Edge/Safari: history & password manager fill */
.login-gate input:-webkit-autofill,
.login-gate input:-webkit-autofill:hover,
.login-gate input:-webkit-autofill:focus,
.login-gate input:-webkit-autofill:active,
.login-gate input:autofill {
  -webkit-text-fill-color: #f1f5f9 !important;
  caret-color: #22d3ee !important;
  /* paint dark fill instead of browser white */
  box-shadow: 0 0 0 1000px #0b1220 inset !important;
  -webkit-box-shadow: 0 0 0 1000px #0b1220 inset !important;
  background-color: #0b1220 !important;
  background-image: none !important;
  transition: background-color 99999s ease-out 0s, background-image 99999s ease-out 0s;
  filter: none !important;
}

/* Firefox */
.login-gate input:-moz-autofill,
.login-gate input:autofill {
  box-shadow: 0 0 0 1000px #0b1220 inset !important;
  background: #0b1220 !important;
  color: #f1f5f9 !important;
}

/* Password row inherits same treatment */
.login-gate .password-field {
  background: transparent !important;
}
.login-gate .password-field input:-webkit-autofill {
  box-shadow: 0 0 0 1000px #0b1220 inset !important;
  -webkit-box-shadow: 0 0 0 1000px #0b1220 inset !important;
}

/* Brand orb: no outer glow / drop-shadow */
.brand-orb {
  filter: none !important;
  box-shadow: none !important;
}
.brand-orb .ae-halo,
.brand-orb .brand-svg .ae-halo {
  opacity: 0.35 !important;
  animation: none !important; /* static soft halo only */
}
.brand-orb img {
  filter: none !important;
}

/* Natural blink: longer open, quick close, slight asymmetry */
.brand-orb .ae-lid {
  transform-box: fill-box;
  transform-origin: center top;
  transform: scaleY(0);
  animation: ae-blink-natural 5.8s ease-in-out infinite !important;
}
.brand-orb .ae-eye-r .ae-lid {
  animation-delay: 0.04s !important;
}
@keyframes ae-blink-natural {
  0%, 88%, 100% { transform: scaleY(0); }
  90% { transform: scaleY(1); }
  92% { transform: scaleY(0); }
  /* occasional double-blink */
  94% { transform: scaleY(0); }
  95.5% { transform: scaleY(1); }
  97% { transform: scaleY(0); }
}
/* Softer look-around */
.brand-orb .ae-pupil {
  animation: ae-look-soft 7s ease-in-out infinite !important;
}
@keyframes ae-look-soft {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(1.5px, 0.5px); }
  50% { transform: translate(-1.2px, 0); }
  75% { transform: translate(0.8px, -0.8px); }
}
'''


def patch_css() -> None:
    if not CSS.exists():
        raise SystemExit(f"missing {CSS}")
    t = CSS.read_text(encoding="utf-8")
    marker = "/* Job 95 fix2 — autofill + icon polish */"
    if marker in t:
        start = t.find(marker)
        t = t[:start] + CSS_BLOCK
    else:
        t = t.rstrip() + "\n\n" + CSS_BLOCK
    CSS.write_text(t, encoding="utf-8")
    print(f"[OK] {CSS}")


def patch_js_remove_glow() -> None:
    if not JS.exists():
        return
    t = JS.read_text(encoding="utf-8")
    # soften brandOrb CSS vars if inline styles set filter
    if "drop-shadow" in t:
        t = t.replace("drop-shadow(0 0 18px rgba(56, 189, 248, 0.35))", "none")
        t = t.replace("drop-shadow(0 0 18px rgba(56, 189, 248, 0.35))", "none")
    JS.write_text(t, encoding="utf-8")
    print(f"[OK] {JS} (glow refs cleaned if any)")


def main() -> int:
    print("Job 95 fix2 — autofill white + icon glow + natural blink")
    patch_css()
    patch_js_remove_glow()
    print(
        """
  # Ctrl+F5 hard refresh
  git add app/static/workspace/styles.css app/static/workspace/app.js
  git commit -m "Job 95 fix2: dark autofill, remove icon glow, natural blink"
  git push origin development
"""
    )
    return 0


if __name__ == "__main__":
    main()
