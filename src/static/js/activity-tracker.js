/* ════════════ EnergyRiskIQ first-party user-behavior tracker ════════════
 * Self-contained, best-effort. Runs on any signed-in page. A tracking failure
 * can never break or slow the host page (everything is wrapped in try/catch and
 * fired in the background). The session token is sent inside the JSON body
 * because navigator.sendBeacon cannot set custom headers.
 */
(function () {
    try {
        var ENDPOINT = '/api/activity/track';
        function getToken() {
            try {
                var s = localStorage.getItem('userSession');
                if (s) {
                    var d = JSON.parse(s);
                    if (d && d.token) return d.token;
                }
            } catch (e) {}
            try { return localStorage.getItem('userToken') || ''; } catch (e) { return ''; }
        }
        // Don't track anonymous visitors (e.g. the signin page before login).
        if (!getToken()) return;

        var queue = [];
        var path = location.pathname || '/';
        var curSection = 'default';
        var sectionStart = Date.now();
        var engagedMs = 0;
        var lastTick = Date.now();
        var visible = (document.visibilityState === 'visible');

        function send(useBeacon) {
            if (!queue.length) return;
            var token = getToken();
            if (!token) { queue = []; return; }
            var body = JSON.stringify({ token: token, events: queue.splice(0, queue.length) });
            try {
                if (useBeacon && navigator.sendBeacon) {
                    navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
                } else {
                    fetch(ENDPOINT, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: body,
                        keepalive: true
                    }).catch(function () {});
                }
            } catch (e) {}
        }
        function enqueue(ev, flushNow) {
            queue.push(ev);
            if (flushNow || queue.length >= 10) send(false);
        }

        // Initial page view
        enqueue({ type: 'page_view', path: path, section: curSection,
                  referrer: document.referrer || '', meta: { sw: screen.width, sh: screen.height } });

        // Engaged-time accounting. engagedMs holds only the UN-FLUSHED delta;
        // flushEngaged() emits it and resets, so the same time is never counted twice.
        function accrue() {
            var now = Date.now();
            if (visible) engagedMs += (now - lastTick);
            lastTick = now;
        }
        function flushEngaged() {
            accrue();
            if (engagedMs > 0) {
                enqueue({ type: 'page_time', path: path, section: curSection, duration_ms: engagedMs });
                engagedMs = 0;
            }
        }
        setInterval(function () {
            accrue();
            if (visible) enqueue({ type: 'heartbeat', path: path, section: curSection });
        }, 60000);

        document.addEventListener('visibilitychange', function () {
            accrue();
            visible = (document.visibilityState === 'visible');
            lastTick = Date.now();
            if (!visible) {
                flushEngaged();
                send(true);
            }
        });
        window.addEventListener('pagehide', function () {
            var secDwell = Date.now() - sectionStart;
            enqueue({ type: 'section_view', path: path, section: curSection, duration_ms: secDwell });
            flushEngaged();
            send(true);
        });

        // Section tracking: wrap showSection if the page has one (account page).
        // Capped retries so non-account pages don't poll forever.
        var hookAttempts = 0;
        function hookSections() {
            if (typeof window.showSection !== 'function') {
                if (hookAttempts++ < 25) setTimeout(hookSections, 400);
                return;
            }
            var orig = window.showSection;
            window.showSection = function (sectionId) {
                try {
                    if (sectionId && sectionId !== curSection) {
                        var dwell = Date.now() - sectionStart;
                        enqueue({ type: 'section_view', path: path, section: curSection, duration_ms: dwell });
                        curSection = sectionId;
                        sectionStart = Date.now();
                        enqueue({ type: 'section_view', path: path, section: sectionId, duration_ms: 0 });
                    }
                } catch (e) {}
                return orig.apply(this, arguments);
            };
        }
        hookSections();

        // CTA click tracking (upgrade / plans / key buttons)
        document.addEventListener('click', function (e) {
            try {
                var el = e.target.closest('button, a');
                if (!el) return;
                var txt = (el.textContent || '').trim().slice(0, 80);
                var oc = (el.getAttribute('onclick') || '');
                var isCta = /upgrade|take offer|view plans|subscribe|buy|checkout/i.test(txt) ||
                            /showSection\('plans'\)/.test(oc);
                if (isCta) {
                    enqueue({ type: 'cta_click', path: path, section: curSection,
                              meta: { label: txt } }, true);
                }
            } catch (err) {}
        }, true);
    } catch (e) {}
})();
