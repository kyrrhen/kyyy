/* ============================================================
   kyrrhen.github.io — 连载漫画动效
   只保留必要交互：返回顶部 / 阅读进度 / 照片筛选 /
   文章展开 / 图片灯箱 / 年份
   ============================================================ */
(function () {
    'use strict';

    var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function rafThrottle(fn) {
        var ticking = false;
        return function () {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(function () {
                fn();
                ticking = false;
            });
        };
    }

    /* ---------- 分镜格滚动交错入场 ---------- */
    function setupPanelReveal() {
        var selector = '.ko-ma, .post-ko-ma, .author-ko-ma, .work-card, .anime-card, .contact-card, .stack-panel';
        var els = document.querySelectorAll(selector);
        if (!els.length) return;

        function isReveal(el) {
            return el.matches(selector);
        }

        els.forEach(function (el) {
            var parent = el.parentElement;
            var idx = 0;
            if (parent) {
                var siblings = Array.prototype.slice.call(parent.children).filter(isReveal);
                idx = siblings.indexOf(el);
            }
            el.style.setProperty('--d', Math.min(idx * 60, 360) + 'ms');
        });

        if (!('IntersectionObserver' in window) || reducedMotion) {
            els.forEach(function (el) { el.classList.add('is-in'); });
            return;
        }

        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-in');
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });

        els.forEach(function (el) { io.observe(el); });
    }

    /* ---------- 漫画翻页载入动画 ---------- */
    function setupPageLoader() {
        function rootPrefix() {
            var dirs = window.location.pathname.split('/').filter(Boolean);
            var depth = Math.max(0, dirs.length - 1);
            return depth ? new Array(depth + 1).join('../') : '';
        }

        function esc(s) {
            return String(s == null ? '' : s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        function showShort() {
            var loader = document.createElement('div');
            loader.className = 'page-loader';
            loader.innerHTML =
                '<div class="loader-book">' +
                    '<span class="loader-sfx">咚</span>' +
                    '<div class="loader-page">' +
                        '<span class="loader-issue">第 1 话 · 连载中</span>' +
                        '<h1>欢迎来到<br>我的小世界</h1>' +
                        '<p>页面正在翻出来，稍等一下。</p>' +
                        '<span class="loader-seal">KY</span>' +
                    '</div>' +
                    '<div class="loader-rule"><i></i></div>' +
                '</div>';
            document.body.appendChild(loader);

            var hidden = false;
            function hide() {
                if (hidden) return;
                hidden = true;
                loader.classList.add('hidden');
                setTimeout(function () { loader.remove(); }, 500);
            }
            setTimeout(hide, 1150);
            window.addEventListener('load', hide);
            setTimeout(hide, 1800);
        }

        function showLong() {
            var loader = document.createElement('div');
            loader.className = 'page-loader long';
            var p = rootPrefix();
            var hidden = false;
            var timers = [];

            function at(ms, fn) {
                timers.push(setTimeout(fn, ms));
            }

            function hide() {
                if (hidden) return;
                hidden = true;
                timers.forEach(clearTimeout);
                loader.classList.add('hidden');
                setTimeout(function () { loader.remove(); }, 500);
            }

            function pageHtml(label, inner, extra) {
                return '<div class="flip-page' + (extra ? ' ' + extra : '') + '">' +
                    '<div class="flip-head"><span>kyrrhen 的小站</span><span>' + esc(label) + '</span></div>' +
                    inner +
                '</div>';
            }

            function build(covers) {
                var flipHtml = pageHtml('PAGE 01',
                    '<div class="flip-cover">' +
                        '<span class="flip-issue">第 1 话 · 序章</span>' +
                        '<h2>欢迎来到<br>我的小世界</h2>' +
                        '<span class="flip-seal">KY</span>' +
                    '</div>'
                );

                var per = 4;
                var variantAt = { 2: 'flutter-r', 4: 'flip-skew', 5: 'pop', 8: 'flutter-u', 12: 'flutter-l', 13: 'flutter-r' };
                var total = 16;
                for (var i = 0; i < total; i++) {
                    var chunk = covers.slice(i * per, i * per + per);
                    var panels = '';
                    for (var j = 0; j < chunk.length; j++) {
                        var c = chunk[j];
                        panels += '<div class="flip-panel"><img src="' + p + '番剧/covers/' + esc(c.img) + '" alt="' + esc(c.title) + '"><span>' + esc(c.title) + '</span></div>';
                    }
                    flipHtml += pageHtml('PAGE ' + String(i + 2), '<div class="flip-panels">' + panels + '</div>', variantAt[i] || '');
                }

                var debrisHtml = '';
                for (var d = 0; d < 12; d++) {
                    var left = (d * 8.3) % 92 + 2;
                    var top = (d * 7.7) % 86 + 4;
                    var dx = ((d % 5) - 2) * 18 + (d % 2 === 0 ? 6 : -6);
                    var dy = -30 - (d % 4) * 12;
                    var dr = (d % 2 === 0 ? 1 : -1) * (160 + d * 37);
                    var dur = (2 + (d % 3) * 0.5).toFixed(2);
                    var delay = (d * 0.23).toFixed(2);
                    debrisHtml += '<i style="left:' + left + 'vw; top:' + top + 'vh; --dx:' + dx + 'vw; --dy:' + dy + 'vh; --dr:' + dr + 'deg; --dur:' + dur + 's; --delay:' + delay + 's"></i>';
                }

                var mosaicHtml = '';
                var cols = 15;
                var rows = 8;
                var totalCells = cols * rows;
                for (var m = 0; m < totalCells; m++) {
                    if (m < covers.length) {
                        var mc = covers[m];
                        var rot = (m % 2 === 0 ? -2 : 2) + 'deg';
                        mosaicHtml += '<div class="cell"><img style="--rot:' + rot + '; animation-delay:' + Math.min(m * 10, 800) + 'ms" src="' + p + '番剧/covers/' + esc(mc.img) + '" alt=""></div>';
                    } else {
                        mosaicHtml += '<div class="cell"></div>';
                    }
                }

                loader.innerHTML =
                    '<div class="stage stage-dark"><span class="seal-big">KY</span><span class="sfx-dong">咚</span></div>' +
                    '<div class="stage stage-flip"><div class="flipbook">' + flipHtml + '</div><div class="debris">' + debrisHtml + '</div></div>' +
                    '<div class="stage stage-mosaic"><div class="mosaic">' + mosaicHtml + '</div></div>' +
                    '<div class="stage stage-speed"><div class="speed-lines"></div><span class="speed-center">第 1 话</span></div>' +
                    '<div class="stage stage-end"><div><span class="end-seal">连载<br>开始</span><p class="end-title">KYRRHEN · 第 1 话</p><p class="end-sub">欢迎来到我的小世界 · 完</p></div></div>' +
                    '<button type="button" class="flip-skip">跳过</button>';
                document.body.appendChild(loader);
                loader.querySelector('.flip-skip').addEventListener('click', hide);

                Array.prototype.forEach.call(loader.querySelectorAll('.mosaic img'), function (img) {
                    var im = new Image();
                    im.src = img.getAttribute('src');
                });

                var pages = loader.querySelectorAll('.flip-page');
                for (var z = 0; z < pages.length; z++) {
                    pages[z].style.zIndex = String(pages.length - z);
                }

                function showStage(id) {
                    var stages = loader.querySelectorAll('.stage');
                    for (var s = 0; s < stages.length; s++) stages[s].classList.remove('active');
                    var el = loader.querySelector('.' + id);
                    if (el) el.classList.add('active');
                }

                function runFlips(pages) {
                    var idx = 0;
                    function flipNext() {
                        if (hidden) return;
                        if (idx >= pages.length) { return; }
                        var page = pages[idx];
                        var isPop = page.classList.contains('pop');
                        var isFlutter = page.classList.contains('flutter-l') || page.classList.contains('flutter-r') || page.classList.contains('flutter-u');
                        var gap = isFlutter || isPop ? 22 : 14;
                        function flipIt() {
                            page.classList.add('flipping');
                            page.addEventListener('animationend', function h(e) {
                                if (e.target !== page) return;
                                page.removeEventListener('animationend', h);
                                page.classList.add('done');
                                idx++;
                                setTimeout(flipNext, gap);
                            }, false);
                        }
                        setTimeout(flipIt, isPop ? 300 : 14);
                    }
                    flipNext();
                }

                showStage('stage-dark');
                at(700, function () { showStage('stage-flip'); });
                at(900, function () {
                    runFlips(pages);
                    at(4300, function () { showStage('stage-mosaic'); });
                });
                at(7200, function () { showStage('stage-speed'); });
                at(8100, function () { showStage('stage-end'); });
                at(9300, hide);
            }

            function ensureCovers(cb) {
                if (window.BANGUMI_COVERS && window.BANGUMI_COVERS.length) {
                    cb(window.BANGUMI_COVERS);
                    return;
                }
                var s = document.createElement('script');
                s.src = p + 'assets/js/covers.js';
                s.onload = function () { cb(window.BANGUMI_COVERS || []); };
                s.onerror = function () { cb([]); };
                document.head.appendChild(s);
            }

            ensureCovers(build);
            at(10000, hide);
        }

        var firstVisit = false;
        try {
            firstVisit = !localStorage.getItem('kyrrhenIntroPlayed');
        } catch (e) {}

        if (firstVisit && !reducedMotion) {
            try {
                localStorage.setItem('kyrrhenIntroPlayed', '1');
            } catch (e) {}
            showLong();
        } else if (!reducedMotion) {
            showShort();
        }

        var foot = document.querySelector('.manga-foot');
        if (foot && !foot.querySelector('.replay-intro')) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'replay-intro';
            btn.textContent = '重看开场';
            btn.title = '播放首次访问动画';
            btn.addEventListener('click', showLong);
            foot.appendChild(btn);
        }
    }

    /* ---------- 章节拟声字 ---------- */
    function setupSfx() {
        var titles = document.querySelectorAll('.chapter-title');
        if (!titles.length) return;
        var words = ['咚', '啪', '咻'];
        var audioCtx = null;
        var unlocked = false;

        function unlockAudio() {
            if (unlocked) return;
            var AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            try {
                audioCtx = new AC();
                if (audioCtx.state === 'suspended') audioCtx.resume();
                unlocked = true;
            } catch (e) {
                unlocked = false;
            }
        }

        window.addEventListener('pointerdown', unlockAudio, { passive: true });
        window.addEventListener('touchstart', unlockAudio, { passive: true });
        window.addEventListener('keydown', unlockAudio, { passive: true });

        function playThump() {
            if (!unlocked || !audioCtx) return;
            try {
                var t = audioCtx.currentTime;
                var osc = audioCtx.createOscillator();
                var gain = audioCtx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(170, t);
                osc.frequency.exponentialRampToValueAtTime(72, t + 0.16);
                gain.gain.setValueAtTime(0.0001, t);
                gain.gain.exponentialRampToValueAtTime(0.12, t + 0.015);
                gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.24);
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start(t);
                osc.stop(t + 0.26);
            } catch (e) {}
        }

        function addSfx(title, word) {
            if (title.querySelector('.sfx-pop')) return;
            var s = document.createElement('span');
            s.className = 'sfx-pop';
            s.textContent = word;
            title.appendChild(s);
            playThump();
        }

        if (!('IntersectionObserver' in window) || reducedMotion) {
            titles.forEach(function (t, i) { addSfx(t, words[i % words.length]); });
            return;
        }

        titles.forEach(function (t, i) {
            var io = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        addSfx(t, words[i % words.length]);
                        io.unobserve(t);
                    }
                });
            }, { threshold: 0.4 });
            io.observe(t);
        });
    }

    /* ---------- 返回顶部 ---------- */
    function setupBackToTop() {
        var btn = document.querySelector('.to-top');
        if (!btn) return;
        var onScroll = rafThrottle(function () {
            btn.classList.toggle('show', window.scrollY > 560);
        });
        window.addEventListener('scroll', onScroll, { passive: true });
        btn.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: reducedMotion ? 'auto' : 'smooth' });
        });
        onScroll();
    }

    /* ---------- 阅读进度条 ---------- */
    function setupReadingProgress() {
        var bar = document.querySelector('.reading-progress');
        if (!bar) return;
        var onScroll = rafThrottle(function () {
            var doc = document.documentElement;
            var total = doc.scrollHeight - doc.clientHeight;
            var pct = total > 0 ? (window.scrollY / total) * 100 : 0;
            bar.style.width = Math.min(pct, 98).toFixed(2) + '%';
        });
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    /* ---------- 照片筛选 ---------- */
    function setupPhotoFilter() {
        var btns = document.querySelectorAll('.filter-btn');
        var cards = document.querySelectorAll('.photo-card, .anime-card');
        if (!btns.length || !cards.length) return;

        btns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                btns.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                var filter = btn.getAttribute('data-filter');

                cards.forEach(function (card) {
                    var cat = card.getAttribute('data-cat') || '';
                    var match = filter === 'all' || cat === filter;

                    if (match) {
                        card.style.display = '';
                        requestAnimationFrame(function () {
                            requestAnimationFrame(function () {
                                card.classList.remove('hide');
                            });
                        });
                    } else {
                        card.classList.add('hide');
                        setTimeout(function () {
                            if (card.classList.contains('hide')) card.style.display = 'none';
                        }, 360);
                    }
                });
            });
        });
    }

    /* ---------- 文章展开 / 收起 ---------- */
    function setupTextExpand() {
        document.querySelectorAll('[data-expand]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var targetId = btn.getAttribute('data-expand');
                var content = document.getElementById(targetId);
                if (!content) return;
                var expanded = content.classList.toggle('expanded');
                content.style.maxHeight = expanded ? content.scrollHeight + 'px' : '220px';
                btn.classList.toggle('expanded', expanded);
                btn.querySelector('.expand-label').textContent = expanded ? '收起' : '展开全文';
            });
        });
    }

    /* ---------- 灯箱（缩放 + 平移） ---------- */
    function setupModal(modalId, imgId) {
        var modal = document.getElementById(modalId);
        var img = document.getElementById(imgId);
        if (!modal || !img) return;

        var scale = 1, tx = 0, ty = 0;
        var dragging = false, startX = 0, startY = 0, lastDist = 0;
        var wrapper = img.parentElement;

        function apply() {
            img.style.transform = 'scale(' + scale + ') translate(' + (tx / scale) + 'px,' + (ty / scale) + 'px)';
        }

        window.openModal = function (src, caption) {
            img.src = src;
            modal.classList.add('active');
            document.body.classList.add('no-scroll');
            scale = 1; tx = 0; ty = 0;
            apply();
            var cap = modal.querySelector('.modal-caption');
            if (cap) cap.textContent = caption || '';
        };

        window.closeModal = function () {
            modal.classList.remove('active');
            document.body.classList.remove('no-scroll');
        };

        window.zoomImage = function (factor) {
            scale = Math.min(Math.max(scale * factor, 0.4), 3.2);
            apply();
        };

        window.resetZoom = function () {
            scale = 1; tx = 0; ty = 0;
            apply();
        };

        modal.addEventListener('wheel', function (e) {
            if (!modal.classList.contains('active')) return;
            e.preventDefault();
            zoomImage(e.deltaY > 0 ? 0.9 : 1.1);
        }, { passive: false });

        wrapper.addEventListener('mousedown', function (e) {
            if (scale <= 1) return;
            dragging = true;
            startX = e.clientX - tx;
            startY = e.clientY - ty;
            wrapper.style.cursor = 'grabbing';
        });
        document.addEventListener('mousemove', function (e) {
            if (!dragging) return;
            tx = e.clientX - startX;
            ty = e.clientY - startY;
            apply();
        });
        document.addEventListener('mouseup', function () {
            dragging = false;
            wrapper.style.cursor = 'grab';
        });

        wrapper.addEventListener('touchstart', function (e) {
            if (e.touches.length === 1 && scale > 1) {
                dragging = true;
                startX = e.touches[0].clientX - tx;
                startY = e.touches[0].clientY - ty;
            } else if (e.touches.length === 2) {
                lastDist = Math.hypot(
                    e.touches[1].clientX - e.touches[0].clientX,
                    e.touches[1].clientY - e.touches[0].clientY
                );
            }
        }, { passive: true });

        wrapper.addEventListener('touchmove', function (e) {
            if (!modal.classList.contains('active')) return;
            e.preventDefault();
            if (e.touches.length === 1 && dragging && scale > 1) {
                tx = e.touches[0].clientX - startX;
                ty = e.touches[0].clientY - startY;
                apply();
            } else if (e.touches.length === 2) {
                var d = Math.hypot(
                    e.touches[1].clientX - e.touches[0].clientX,
                    e.touches[1].clientY - e.touches[0].clientY
                );
                zoomImage(d / lastDist);
                lastDist = d;
            }
        }, { passive: false });

        wrapper.addEventListener('touchend', function () {
            dragging = false;
        });

        modal.addEventListener('click', function (e) {
            if (e.target === modal || e.target.closest('.modal-close')) closeModal();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeModal();
        });
    }

    /* ---------- 年份 ---------- */
    function setupYear() {
        document.querySelectorAll('[data-year]').forEach(function (el) {
            el.textContent = new Date().getFullYear();
        });
    }

    function init() {
        setupPageLoader();
        setupPanelReveal();
        setupSfx();
        setupBackToTop();
        setupReadingProgress();
        setupPhotoFilter();
        setupTextExpand();
        setupYear();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.setupBackToTop = setupBackToTop;
    window.setupPageLoader = setupPageLoader;
    window.setupPanelReveal = setupPanelReveal;
    window.setupSfx = setupSfx;
    window.setupReadingProgress = setupReadingProgress;
    window.setupPhotoFilter = setupPhotoFilter;
    window.setupTextExpand = setupTextExpand;
    window.setupModal = setupModal;
    window.openModal = function () {};
    window.closeModal = function () {};
    window.zoomImage = function () {};
    window.resetZoom = function () {};
})();
