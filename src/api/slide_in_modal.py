"""
Contextual slide-in signup modal — shared across all public pages.

Usage (inside an f-string builder):
    from src.api.slide_in_modal import slide_in_modal
    ...
    return f\"\"\"
    ...
    {slide_in_modal('page-key', 'Title Text', ['Para 1.', 'Para 2.'], ['Bullet 1', 'Bullet 2'])}
    </body></html>\"\"\"

page_key   — unique per page; used for the localStorage dismiss key
title      — small-caps heading inside the modal
intro_lines — list of paragraph strings (contextual copy, left-aligned)
bullets     — list of checkmark bullet strings
"""


def slide_in_modal(page_key: str, title: str, intro_lines: list, bullets: list) -> str:
    intro_html   = ''.join(f'<p>{line}</p>' for line in intro_lines)
    bullets_html = ''.join(f'<li>{b}</li>' for b in bullets)
    dismiss_key  = f'eiriq_si_{page_key}_dismissed'

    return f"""
<!-- ── SLIDE-IN SIGNUP MODAL ({page_key}) ─────────────────────────────── -->
<style>
#bsi-overlay {{
  position: fixed;
  right: 30px;
  bottom: 30px;
  width: 400px;
  max-width: calc(100vw - 40px);
  z-index: 9999;
  transform: translateX(calc(100% + 40px));
  transition: transform 0.85s cubic-bezier(0.22, 0.61, 0.36, 1);
  pointer-events: none;
}}
#bsi-overlay.bsi-visible {{
  transform: translateX(0);
  pointer-events: auto;
}}
#bsi-box {{
  background: #0d1421;
  border: 1.5px solid #475569;
  border-radius: 6px;
  padding: 24px 22px 22px;
  font-family: 'IBM Plex Mono', 'Courier New', monospace;
  color: #e2e8f0;
  box-shadow: 0 8px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(248,113,18,0.06);
  position: relative;
}}
#bsi-close {{
  position: absolute;
  top: 12px;
  right: 14px;
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 4px;
  transition: color 0.15s;
  font-family: inherit;
}}
#bsi-close:hover {{ color: #e2e8f0; }}
#bsi-title {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #94a3b8;
  text-transform: uppercase;
  margin-bottom: 14px;
  padding-right: 24px;
}}
#bsi-body p {{
  font-size: 13.5px;
  line-height: 1.6;
  color: #cbd5e1;
  margin: 0 0 10px;
}}
#bsi-bullets {{
  margin: 14px 0 18px;
  padding: 0;
  list-style: none;
}}
#bsi-bullets li {{
  font-size: 12.5px;
  color: #94a3b8;
  padding: 3px 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}}
#bsi-bullets li::before {{
  content: '✓';
  color: #22c55e;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 1px;
}}
#bsi-divider {{
  border: none;
  border-top: 1px solid #1e293b;
  margin: 16px 0;
}}
#bsi-form-wrap {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}}
#bsi-email {{
  width: 100%;
  max-width: 320px;
  padding: 10px 14px;
  background: #0b0f1a;
  border: 1.5px solid #64748b;
  border-radius: 4px;
  color: #e2e8f0;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  box-sizing: border-box;
  text-align: center;
  transition: border-color 0.2s;
}}
#bsi-email::placeholder {{ color: #475569; }}
#bsi-email:focus {{ border-color: #f97316; }}
#bsi-submit {{
  width: 100%;
  max-width: 320px;
  padding: 11px 16px;
  background: #f97316;
  border: none;
  border-radius: 4px;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  letter-spacing: 0.03em;
  transition: background 0.15s, opacity 0.15s;
}}
#bsi-submit:hover {{ background: #ea6e10; }}
#bsi-submit:disabled {{ opacity: 0.5; cursor: default; }}
#bsi-note {{
  font-size: 11px;
  color: #475569;
  margin-top: 2px;
}}
#bsi-error {{
  font-size: 12px;
  color: #ef4444;
  display: none;
  text-align: center;
}}
#bsi-thankyou {{
  display: none;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
  padding: 4px 0 6px;
}}
#bsi-thankyou .bsi-ty-icon {{ font-size: 28px; margin-bottom: 2px; }}
#bsi-thankyou .bsi-ty-head {{ font-size: 14px; font-weight: 700; color: #22c55e; }}
#bsi-thankyou .bsi-ty-sub  {{ font-size: 12.5px; color: #94a3b8; line-height: 1.5; }}
#bsi-thankyou button {{
  margin-top: 6px;
  padding: 8px 20px;
  background: none;
  border: 1px solid #334155;
  border-radius: 4px;
  color: #64748b;
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}}
#bsi-thankyou button:hover {{ color: #e2e8f0; border-color: #64748b; }}
@media (max-width: 600px) {{
  #bsi-overlay {{
    right: 0; bottom: 0; left: 0;
    width: 100%; max-width: 100%;
    transform: translateY(calc(100% + 20px));
  }}
  #bsi-overlay.bsi-visible {{ transform: translateY(0); }}
  #bsi-box {{
    border-radius: 12px 12px 0 0;
    border-left: none; border-right: none; border-bottom: none;
    padding: 20px 18px 28px;
  }}
}}
</style>

<div id="bsi-overlay" role="dialog" aria-modal="true" aria-label="{title}">
  <div id="bsi-box">
    <button id="bsi-close" aria-label="Dismiss">&#x2715;</button>
    <div id="bsi-title">{title}</div>
    <div id="bsi-body">{intro_html}</div>
    <ul id="bsi-bullets">{bullets_html}</ul>
    <hr id="bsi-divider">
    <div id="bsi-form-wrap">
      <input id="bsi-email" type="email" placeholder="your@email.com" autocomplete="email" aria-label="Email address">
      <div id="bsi-error"></div>
      <button id="bsi-submit">Unlock Deeper Intelligence</button>
      <div id="bsi-note">Free EnergyRiskIQ account &mdash; no card required</div>
    </div>
    <div id="bsi-thankyou">
      <div class="bsi-ty-icon">&#9989;</div>
      <div class="bsi-ty-head">Thank You!</div>
      <div class="bsi-ty-sub">Please check your inbox and verify your email<br>to activate your account.</div>
      <button id="bsi-ty-close">Close This Window</button>
    </div>
  </div>
</div>

<script>
(function() {{
  var DISMISS_KEY = '{dismiss_key}';
  var SESSION_KEY = 'eiriq_si_shown';
  var DISMISS_TTL = 7 * 24 * 60 * 60 * 1000;

  function isLoggedIn() {{
    return !!(localStorage.getItem('userToken') || localStorage.getItem('sessionToken'));
  }}
  function isDismissedRecently() {{
    var ts = localStorage.getItem(DISMISS_KEY);
    return ts ? (Date.now() - parseInt(ts, 10)) < DISMISS_TTL : false;
  }}
  function hasShownThisSession() {{
    return !!sessionStorage.getItem(SESSION_KEY);
  }}
  function shouldShow() {{
    return !isLoggedIn() && !isDismissedRecently() && !hasShownThisSession();
  }}
  function showModal() {{
    if (!shouldShow()) return;
    sessionStorage.setItem(SESSION_KEY, '1');
    document.getElementById('bsi-overlay').classList.add('bsi-visible');
  }}
  function hideModal() {{
    document.getElementById('bsi-overlay').classList.remove('bsi-visible');
  }}
  function dismiss() {{
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    hideModal();
  }}

  var triggered = false;
  function trigger() {{
    if (triggered) return;
    triggered = true;
    showModal();
  }}

  var timeoutId = setTimeout(trigger, 25000);
  function onScroll() {{
    var scrolled = window.scrollY || window.pageYOffset;
    var docH = document.documentElement.scrollHeight - window.innerHeight;
    if (docH > 0 && scrolled / docH >= 0.30) {{
      clearTimeout(timeoutId);
      trigger();
      window.removeEventListener('scroll', onScroll, {{ passive: true }});
    }}
  }}
  window.addEventListener('scroll', onScroll, {{ passive: true }});

  document.getElementById('bsi-close').addEventListener('click', dismiss);
  document.getElementById('bsi-ty-close').addEventListener('click', dismiss);

  document.getElementById('bsi-submit').addEventListener('click', function() {{
    var emailEl = document.getElementById('bsi-email');
    var errEl   = document.getElementById('bsi-error');
    var email   = emailEl.value.trim();
    errEl.style.display = 'none'; errEl.textContent = '';
    if (!email || !email.includes('@')) {{
      errEl.textContent = 'Please enter a valid email address.';
      errEl.style.display = 'block';
      emailEl.focus(); return;
    }}
    var btn = document.getElementById('bsi-submit');
    btn.disabled = true; btn.textContent = 'Sending\u2026';
    fetch('/users/signup', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ email: email }})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data && data.success) {{
        document.getElementById('bsi-title').style.display    = 'none';
        document.getElementById('bsi-body').style.display     = 'none';
        document.getElementById('bsi-bullets').style.display  = 'none';
        document.getElementById('bsi-divider').style.display  = 'none';
        document.getElementById('bsi-form-wrap').style.display = 'none';
        document.getElementById('bsi-thankyou').style.display = 'flex';
      }} else {{
        var msg = (data && data.detail) ? data.detail : 'Something went wrong. Please try again.';
        errEl.textContent = msg; errEl.style.display = 'block';
        btn.disabled = false; btn.textContent = 'Unlock Deeper Intelligence';
      }}
    }})
    .catch(function() {{
      errEl.textContent = 'Network error. Please try again.';
      errEl.style.display = 'block';
      btn.disabled = false; btn.textContent = 'Unlock Deeper Intelligence';
    }});
  }});

  document.getElementById('bsi-email').addEventListener('keydown', function(e) {{
    if (e.key === 'Enter') document.getElementById('bsi-submit').click();
  }});
}})();
</script>
<!-- ── END SLIDE-IN MODAL ({page_key}) ───────────────────────────────── -->
"""
