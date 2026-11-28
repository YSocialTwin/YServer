var MB_FEED = (function() {
    var AUTO_REFRESH_INTERVAL_MS = 30000;
    var TOP_REFRESH_SCROLL_THRESHOLD = 220;

    var state = {
        config: {},
        apiEndpoint: null,
        postsContainer: null,
        refreshNotice: null,
        refreshButton: null,
        autoRefreshTimer: null,
        isRefreshing: false,
        liveRefreshEnabled: false
    };

    function buildApiEndpoint(config) {
        return '/' + config.expId + '/api/feed/' + config.userId + '/' + config.timeline + '/' + config.mode;
    }

    function init() {
        var config = window.YS_DATA_MB_FEED || {};
        if (config.page === undefined) {
            return;
        }

        stopAutoRefresh();

        state.config = config;
        state.apiEndpoint = buildApiEndpoint(config);
        state.postsContainer = document.getElementById('posts-container');
        state.liveRefreshEnabled = Number(config.page || 1) === 1;

        if (window.InfiniteScroll && config.infiniteScrollEnabled !== false) {
            InfiniteScroll.init({
                apiEndpoint: state.apiEndpoint,
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }

        if (!state.postsContainer) {
            return;
        }

        ensureRefreshNotice();
        hideRefreshNotice();

        if (state.liveRefreshEnabled) {
            startAutoRefresh();
        }
    }

    function ensureRefreshNotice() {
        if (state.refreshNotice && state.refreshButton) {
            return;
        }

        var existingNotice = document.getElementById('ys-feed-refresh-notice');
        if (!existingNotice) {
            existingNotice = document.createElement('div');
            existingNotice.id = 'ys-feed-refresh-notice';
            existingNotice.className = 'ys-feed-refresh-notice';
            existingNotice.hidden = true;
            existingNotice.innerHTML = [
                '<button type="button" class="ys-feed-refresh-notice__button">',
                '  <i data-feather="rotate-cw"></i>',
                '  <span>' + YI18n.t('New posts available') + '</span>',
                '</button>'
            ].join('');
            state.postsContainer.parentNode.insertBefore(existingNotice, state.postsContainer);
        }

        state.refreshNotice = existingNotice;
        state.refreshButton = existingNotice.querySelector('.ys-feed-refresh-notice__button');

        if (state.refreshButton && !state.refreshButton.dataset.bound) {
            state.refreshButton.addEventListener('click', function() {
                refreshFeed(true);
            });
            state.refreshButton.dataset.bound = '1';
        }
    }

    function initializeDynamicFeedContent(scope) {
        if (!scope) {
            return;
        }

        scope.querySelectorAll('[data-demo-src]').forEach(function(img) {
            var nextSrc = img.getAttribute('data-demo-src');
            if (nextSrc) {
                img.setAttribute('src', nextSrc);
            }
        });

        scope.querySelectorAll('[data-demo-background]').forEach(function(node) {
            var nextBackground = node.getAttribute('data-demo-background');
            if (nextBackground) {
                node.style.backgroundImage = "url('" + nextBackground + "')";
            }
        });

        if (window.feather) {
            window.feather.replace();
        }
    }

    function getTopRenderedPostId() {
        if (!state.postsContainer) {
            return null;
        }
        return extractTopPostId(state.postsContainer);
    }

    function extractTopPostId(root) {
        if (!root || !root.querySelector) {
            return null;
        }
        var firstPost = root.querySelector('[id^="feed-post-"]');
        if (!firstPost) {
            return null;
        }
        var postId = String(firstPost.id || '').replace('feed-post-', '');
        return postId || null;
    }

    function extractTopPostIdFromHtml(html) {
        if (!html || !html.trim()) {
            return null;
        }
        var temp = document.createElement('div');
        temp.innerHTML = html;
        return extractTopPostId(temp);
    }

    function shouldAutoRefreshFeed() {
        if (!state.liveRefreshEnabled) {
            return false;
        }
        if (document.hidden) {
            return false;
        }
        if (state.isRefreshing) {
            return false;
        }
        return window.scrollY < TOP_REFRESH_SCROLL_THRESHOLD;
    }

    function showRefreshNotice() {
        if (!state.refreshNotice) {
            return;
        }
        state.refreshNotice.hidden = false;
        state.refreshNotice.classList.add('is-visible');
    }

    function hideRefreshNotice() {
        if (!state.refreshNotice) {
            return;
        }
        state.refreshNotice.hidden = true;
        state.refreshNotice.classList.remove('is-visible');
    }

    function fetchFeedPage(page) {
        return fetch(state.apiEndpoint + '/' + page, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        }).then(function(response) {
            if (!response.ok) {
                throw new Error(YI18n.t('Unable to refresh feed.'));
            }
            return response.json();
        });
    }

    function replaceFeedHtml(html) {
        if (!state.postsContainer) {
            return;
        }

        state.postsContainer.innerHTML = html;
        initializeDynamicFeedContent(state.postsContainer);
        hideRefreshNotice();

        if (window.InfiniteScroll && (state.config && state.config.infiniteScrollEnabled !== false)) {
            InfiniteScroll.init({
                apiEndpoint: state.apiEndpoint,
                postsContainerId: 'posts-container',
                initialPage: 1
            });
        }
    }

    function refreshFeed(scrollToTop) {
        if (!state.liveRefreshEnabled || state.isRefreshing) {
            return Promise.resolve();
        }

        state.isRefreshing = true;
        return fetchFeedPage(1)
            .then(function(payload) {
                if (payload && payload.html) {
                    replaceFeedHtml(payload.html);
                    if (scrollToTop) {
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                    }
                }
            })
            .catch(function() {
                // Silent failure to preserve feed usability.
            })
            .finally(function() {
                state.isRefreshing = false;
            });
    }

    function probeForNewPosts() {
        if (!state.liveRefreshEnabled || state.isRefreshing) {
            return;
        }

        fetchFeedPage(1)
            .then(function(payload) {
                if (!payload || !payload.html) {
                    return;
                }
                var currentTop = getTopRenderedPostId();
                var nextTop = extractTopPostIdFromHtml(payload.html);
                if (!nextTop) {
                    return;
                }
                if (currentTop === null || nextTop !== currentTop) {
                    showRefreshNotice();
                }
            })
            .catch(function() {
                // Ignore silent probe failures.
            });
    }

    function startAutoRefresh() {
        if (!state.liveRefreshEnabled) {
            return;
        }
        stopAutoRefresh();
        state.autoRefreshTimer = window.setInterval(function() {
            if (!shouldAutoRefreshFeed()) {
                probeForNewPosts();
                return;
            }
            refreshFeed(false);
        }, AUTO_REFRESH_INTERVAL_MS);
    }

    function stopAutoRefresh() {
        if (state.autoRefreshTimer) {
            window.clearInterval(state.autoRefreshTimer);
            state.autoRefreshTimer = null;
        }
    }


    // "Your recommender system" box: show the algorithm of the tab that is now displayed.
    function updateRecsysBox(info) {
        var box = document.getElementById('ys-recsys-box');
        if (!box || !info) { return; }
        box.setAttribute('data-recsys', info.name || '');
        var pill = box.querySelector('.ys-recsys-pill');
        if (pill) { pill.textContent = info.label || info.name || ''; }
        var how = box.querySelector('.ys-recsys-how p');
        if (how) { how.textContent = info.description || ''; }
    }

    // Switch between the feed tabs (Home / Recent / Friends / Popular) without reloading the page.
    var popBound = false;
    function switchTab(tab, href) {
        var cfg = window.YS_DATA_MB_FEED;
        if (!cfg || cfg.infiniteScrollEnabled === false || !state.postsContainer) {
            return false;
        }
        stopAutoRefresh();
        var url = '/' + cfg.expId + '/api/feed/' + cfg.userId + '/' + tab + '/' + cfg.mode + '/1';
        state.postsContainer.style.opacity = '.45';
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
            .then(function(response) {
                if (!response.ok) { throw new Error('tab'); }
                return response.json();
            })
            .then(function(payload) {
                // new URL first: the annotation add-on reads the tab from the page URL (Referer) of its requests
                if (window.history && window.history.pushState) {
                    window.history.pushState({ tab: tab }, '', href);
                    if (!popBound) {
                        popBound = true;
                        window.addEventListener('popstate', function() { window.location.reload(); });
                    }
                }
                // the feed shown is about to change (another recommender): add-ons drop what they know about the posts of the old one
                try { window.dispatchEvent(new Event('ys:feed-swapped')); } catch (e) {}
                state.postsContainer.innerHTML = payload.html || '';
                initializeDynamicFeedContent(state.postsContainer);
                updateRecsysBox(payload.recsys);
                cfg.timeline = tab;
                cfg.page = 1;
                init();
                document.querySelectorAll('.bsky-feedhead .bsky-tab').forEach(function(t) {
                    var on = t.getAttribute('data-tab') === tab;
                    t.classList.toggle('is-active', on);
                    t.setAttribute('aria-selected', on ? 'true' : 'false');
                });
                // "Your annotations" box listens to this event and reloads its statistics (now scoped to the tab)
                try { window.dispatchEvent(new Event('ys:annotation-saved')); } catch (e) {}
                window.scrollTo({ top: 0 });
            })
            .catch(function() {
                window.location.href = href;
            })
            .finally(function() {
                state.postsContainer.style.opacity = '';
            });
        return true;
    }

    // Read the page again (same address) and swap what depends on the feed -- posts, pagination, the "ranked last" note, the
    // recommender box -- without leaving the page. Works with infinite scrolling and with classic pagination.
    function softReload(url) {
        var current = state.postsContainer;
        if (!current || !window.fetch || !window.DOMParser) { return Promise.reject(new Error('unsupported')); }
        stopAutoRefresh();
        current.style.opacity = '.45';
        return fetch(url || window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
            .then(function(response) {
                if (!response.ok) { throw new Error('reload'); }
                return response.text();
            })
            .then(function(html) {
                var doc = new DOMParser().parseFromString(html, 'text/html');
                var next = doc.getElementById('posts-container');
                if (!next) { throw new Error('reload'); }
                // the feed shown is about to change (another recommender): add-ons drop what they know about the posts of the old one
                try { window.dispatchEvent(new Event('ys:feed-swapped')); } catch (e) {}
                current.innerHTML = next.innerHTML;
                initializeDynamicFeedContent(current);
                ['.ys-pagination', '#ys-recsys-box'].forEach(function(selector) {
                    var a = document.querySelector(selector), b = doc.querySelector(selector);
                    if (a && b) { a.replaceWith(b); } else if (a) { a.remove(); }
                });
                var oldNote = document.querySelector('.ys-rank-last-note'), newNote = doc.querySelector('.ys-rank-last-note');
                if (oldNote && newNote) { oldNote.replaceWith(newNote); }
                else if (oldNote) { oldNote.remove(); }
                else if (newNote) { current.parentNode.insertBefore(newNote, current); }
                initializeDynamicFeedContent(document.querySelector('.ys-rank-last-note') || current);
                init();
                try { window.dispatchEvent(new Event('ys:annotation-saved')); } catch (e) {}
            })
            .finally(function() { current.style.opacity = ''; });
    }

    document.addEventListener('click', function(event) {
        var link = event.target.closest ? event.target.closest('.bsky-feedhead .bsky-tab[data-tab]') : null;
        if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button) {
            return;
        }
        if (switchTab(link.getAttribute('data-tab'), link.getAttribute('href'))) {
            event.preventDefault();
        }
    });

    document.addEventListener('DOMContentLoaded', init);
    window.addEventListener('beforeunload', stopAutoRefresh);

    return {
        init: init,
        probeForNewPosts: probeForNewPosts,
        refreshFeed: refreshFeed,
        switchTab: switchTab,
        softReload: softReload
    };
})();
