#!/usr/bin/env python3
"""
Job 96 — Fix post-login blank white screen.

Root causes addressed:
1. #app shown while no view is active → white empty shell
2. onboard-card forced transparent by later CSS → invisible content
3. showOnboardingWizard did not force visibility / hide #app
4. body default white background under the shell
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
JS = ROOT / "app" / "static" / "workspace" / "app.js"
CSS = ROOT / "app" / "static" / "workspace" / "styles.css"

CSS_FIX = r'''
/* Job 96 — post-login onboarding must never be a blank white sheet */
html, body {
  background: #0b1220 !important;
  color: #e2e8f0;
}
#app.hidden { display: none !important; }
#onboardingWizard {
  position: fixed !important;
  inset: 0 !important;
  z-index: 9999 !important;
  display: grid !important;
  place-items: center !important;
  min-height: 100vh !important;
  background: #0b1220 !important;
  color: #e2e8f0 !important;
}
#onboardingWizard.hidden {
  display: none !important;
}
#onboardingWizard .onboard-card {
  position: relative;
  z-index: 1;
  width: min(520px, 94vw) !important;
  padding: 1.75rem !important;
  border-radius: 16px !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  background: rgba(15, 23, 42, 0.92) !important;
  backdrop-filter: blur(16px) !important;
  color: #e2e8f0 !important;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45) !important;
}
#onboardingWizard h2 { color: #f8fafc !important; margin: 0.25rem 0 0.5rem; }
#onboardingWizard .muted { color: #94a3b8 !important; }
#onboardingWizard .primary.block {
  margin-top: 1rem;
  width: 100%;
  border: none;
  border-radius: 999px;
  padding: 0.75rem 1rem;
  font-weight: 600;
  color: #0b1220;
  cursor: pointer;
  background: linear-gradient(120deg, #22d3ee, #818cf8 50%, #e879f9);
}
'''


def patch_css():
    t = CSS.read_text(encoding="utf-8")
    marker = "/* Job 96 — post-login onboarding"
    if marker in t:
        t = t[: t.find(marker)] + CSS_FIX
    else:
        t = t.rstrip() + "\n\n" + CSS_FIX
    CSS.write_text(t, encoding="utf-8")
    print("[OK] styles.css Job 96 onboarding visibility")


def patch_js():
    t = JS.read_text(encoding="utf-8")

    new_show = '''  function showOnboardingWizard(step) {
    const w = $("onboardingWizard");
    if (!w) {
      console.warn("onboardingWizard missing");
      return;
    }
    w.classList.remove("hidden");
    w.style.display = "grid";
    w.style.visibility = "visible";
    w.style.opacity = "1";
    w.style.zIndex = "9999";
    // Keep main workspace hidden until onboarding finishes
    const app = $("app");
    if (app) {
      app.classList.add("hidden");
      app.style.display = "none";
    }
    setOnboardStep(step || 1);
  }
  function hideOnboardingWizard() {
    const w = $("onboardingWizard");
    if (w) {
      w.classList.add("hidden");
      w.style.display = "none";
    }
    const app = $("app");
    if (app && state.accessToken) {
      app.classList.remove("hidden");
      app.style.display = "";
    }
  }
'''

    # Replace existing function pair
    t2, n = re.subn(
        r"  function showOnboardingWizard\(step\) \{[\s\S]*?\n  function hideOnboardingWizard\(\) \{[\s\S]*?\n  \}\n",
        new_show,
        t,
        count=1,
    )
    if n != 1:
        # try insert before routePostLoginOnboarding
        if "function showOnboardingWizard" in t:
            t2 = re.sub(
                r"  function showOnboardingWizard\(step\) \{[\s\S]*?\n  \}\n  function hideOnboardingWizard\(\) \{[\s\S]*?\n  \}\n",
                new_show,
                t,
                count=1,
            )
        else:
            t2 = t.replace(
                "  async function routePostLoginOnboarding()",
                new_show + "  async function routePostLoginOnboarding()",
                1,
            )
    t = t2

    # Harden routePostLoginOnboarding
    better_route = '''  async function routePostLoginOnboarding() {
    try {
      if (!state.companyId) {
        // No company yet — still show step 1 if wizard exists
        showOnboardingWizard(1);
        return;
      }
      let company = null;
      try {
        company = await api(`/companies/${state.companyId}`);
      } catch (e) {
        console.warn("company fetch failed", e);
        showOnboardingWizard(1);
        return;
      }
      state.onboardingStatus = (company && company.onboarding_status) || "pending";
      if (state.onboardingStatus !== "complete") {
        showOnboardingWizard(1);
        return;
      }
      let agents = [];
      try { agents = await api(`/companies/${state.companyId}/agents`); } catch (_) {}
      if (!agents || !agents.length) {
        showOnboardingWizard(2);
        return;
      }
      hideOnboardingWizard();
      try { showView(defaultLandingView()); } catch (_) {}
    } catch (err) {
      console.warn("routePostLoginOnboarding", err);
      showOnboardingWizard(1);
    }
  }
'''
    t3, n3 = re.subn(
        r"  async function routePostLoginOnboarding\(\) \{[\s\S]*?\n  \}\n",
        better_route,
        t,
        count=1,
    )
    if n3 == 1:
        t = t3
    else:
        print("[WARN] routePostLoginOnboarding not replaced")

    # After setConnected(true) on login success, ensure onboarding runs
    # already has await routePostLoginOnboarding at 1287 - ok

    JS.write_text(t, encoding="utf-8")
    print("[OK] app.js show/hide onboarding + route hardened")


def main():
    print("Job 96 — blank white post-login fix")
    if not JS.exists():
        raise SystemExit("run from repo root")
    patch_css()
    patch_js()
    print(
        """
  Ctrl+F5 /workspace → login again
  Expect: dark aurora onboarding card (Company → Hire → Configure)
  NOT a blank white page.

  git add app/static/workspace/app.js app/static/workspace/styles.css
  git commit -m "Job 96: fix blank white post-login; force onboarding visibility"
  git push origin development
"""
    )


if __name__ == "__main__":
    main()
