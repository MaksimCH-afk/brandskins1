(function () {
  'use strict';

  var PARTNER_OFFER_URL = 'https://money.com/';

  var openPartnerOffer = function () {
    window.open(PARTNER_OFFER_URL, '_blank', 'noopener,noreferrer');
  };

  var shouldSkipPartnerRedirect = function (anchor) {
    if (anchor.closest('.lang-switcher')) {
      return true;
    }
    if (anchor.hasAttribute('data-auth') || anchor.hasAttribute('data-mode')) {
      return true;
    }
    if (anchor.closest('.footer')) {
      return true;
    }
    if (anchor.closest('.socials') || anchor.closest('.author-socials')) {
      return true;
    }
    if (anchor.classList.contains('skip-link')) {
      return true;
    }
    var rawHref = anchor.getAttribute('href');
    if (rawHref === null || rawHref === '') {
      return true;
    }
    if (rawHref === '#') {
      return false;
    }
    if (rawHref.startsWith('#')) {
      return true;
    }
    try {
      var url = new URL(rawHref, window.location.href);
      var protocol = url.protocol.toLowerCase();
      if (protocol === 'mailto:' || protocol === 'tel:' || protocol === 'sms:' || protocol === 'javascript:' || protocol === 'data:') {
        return true;
      }
      if (url.pathname.toLowerCase().endsWith('.apk')) {
        return true;
      }
      if (url.origin === window.location.origin) {
        return true;
      }
    } catch (err) {
      return true;
    }
    return false;
  };

  var header = document.getElementById('header');
  var burger = document.getElementById('burger');
  var drawer = document.getElementById('drawer');
  var overlay = document.getElementById('drawerOverlay');
  var authOverlay = document.getElementById('authOverlay');
  var authModal = document.getElementById('authModal');

  var onScroll = function () {
    if (!header) return;
    header.classList.toggle('scrolled', window.scrollY > 12);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  var setDrawerOpen = function (isOpen) {
    if (!drawer || !overlay || !burger) return;
    drawer.classList.toggle('open', isOpen);
    overlay.classList.toggle('open', isOpen);
    document.body.classList.toggle('no-scroll', isOpen);
    burger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  };

  if (burger) burger.addEventListener('click', function () { setDrawerOpen(true); });
  var drawerClose = document.getElementById('drawerClose');
  if (drawerClose) drawerClose.addEventListener('click', function () { setDrawerOpen(false); });
  if (overlay) overlay.addEventListener('click', function () { setDrawerOpen(false); });
  if (drawer) {
    drawer.querySelectorAll('[data-close]').forEach(function (el) {
      el.addEventListener('click', function () { setDrawerOpen(false); });
    });
  }

  var GAMES = [
    { n: 'Game Title 01',    p: 'Provider 01', c: 'slots',   b: 'hot',  s: '777' },
    { n: 'Game Title 02',       p: 'Provider 02',     c: 'slots',   b: '',     s: '€' },
    { n: 'Game Title 03',   p: 'Provider 03',        c: 'slots',   b: '',     s: '◆' },
    { n: 'Game Title 04',      p: 'Provider 04',c: 'slots',   b: 'new',  s: '★' },
    { n: 'Game Title 05',     p: 'Provider 05',       c: 'slots',   b: '',     s: '777' },
    { n: 'Game Title 06', p: 'Provider 06',     c: 'live',    b: 'hot',  s: '◉' },
    { n: 'Game Title 07',  p: 'Provider 07',     c: 'live',    b: '',     s: 'A♠' },
    { n: 'Game Title 08',   p: 'Provider 08',c: 'live',    b: '',     s: '♦' },
    { n: 'Game Title 09',    p: 'Provider 09',     c: 'live',    b: 'new',  s: '⚄' },
    { n: 'Game Title 10', p: 'Provider 10',        c: 'table',   b: '',     s: '◉' },
    { n: 'Game Title 11',p: 'Provider 11',      c: 'table',   b: '',     s: 'A♠' },
    { n: 'Game Title 12',   p: 'Provider 12',     c: 'table',   b: '',     s: 'K♥' },
    { n: 'Game Title 13', p: 'Provider 13',   c: 'jackpot', b: 'hot',  s: '€' },
    { n: 'Game Title 14',   p: 'Provider 14',     c: 'jackpot', b: '',     s: '★' },
    { n: 'Game Title 15', p: 'Provider 15',   c: 'jackpot', b: 'new',  s: '777' },
    { n: 'Game Title 16',     p: 'Provider 16',  c: 'slots',   b: '',     s: '◆' }
  ];

  var grid = document.getElementById('gamesGrid');

  var tileHTML = function (g, i) {
    var badge = g.b ? '<span class="game__badge ' + (g.b === 'hot' ? 'hot' : '') + '">' + g.b + '</span>' : '';
    var label = g.n.replace(/"/g, '&quot;');
    return '<article class="game" data-cat="' + g.c + '">' +
      badge +
      '<a href="#" class="game__link" rel="nofollow" target="_blank" aria-label="Play ' + label + '">' +
      '<div class="game__art"><div class="cover cover--' + (i % 6) + '">' +
        '<span class="spark s1"></span><span class="spark s2"></span>' +
        '<span class="cover__sym">' + g.s + '</span>' +
        '<span class="cover__brand">' + g.p + '</span>' +
      '</div>' +
      '<div class="game__play"><span class="btn btn--gold">▶ Play</span></div></div>' +
      '<div class="game__meta"><b>' + g.n + '</b><span>' + g.p + '</span></div>' +
      '</a></article>';
  };

  var renderGames = function (cat) {
    if (!grid) return;
    var list = cat === 'all' ? GAMES : GAMES.filter(function (g) { return g.c === cat; });
    grid.innerHTML = list.map(tileHTML).join('');
  };

  if (grid) {
    renderGames('all');
    var tabs = document.getElementById('gameTabs');
    if (tabs) {
      tabs.addEventListener('click', function (e) {
        var btn = e.target.closest('.tab');
        if (!btn) return;
        tabs.querySelectorAll('.tab').forEach(function (t) {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        renderGames(btn.getAttribute('data-cat'));
      });
    }
  }

  var closeAuth = function () {
    if (!authOverlay) return;
    authOverlay.classList.remove('open');
    document.body.classList.remove('no-scroll');
  };

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('[data-auth]');
    if (trigger) {
      e.preventDefault();
      setDrawerOpen(false);
      openPartnerOffer();
      return;
    }
    var link = e.target.closest('a');
    if (!link || shouldSkipPartnerRedirect(link)) {
      return;
    }
    e.preventDefault();
    openPartnerOffer();
  });

  var authClose = document.getElementById('authClose');
  if (authClose) authClose.addEventListener('click', closeAuth);
  if (authOverlay) {
    authOverlay.addEventListener('click', function (e) {
      if (e.target === authOverlay) closeAuth();
    });
  }

  var LANG_STORAGE_KEY = 'brandname-locale';

  var LOCALE_META = {
    'en-IE': { code: 'IE', label: 'English', flag: 'ie' },
    'da-DK': { code: 'DK', label: 'Dansk', flag: 'dk' },
    'cs-CZ': { code: 'CZ', label: 'Čeština', flag: 'cz' },
    'el-GR': { code: 'GR', label: 'Ελληνικά', flag: 'gr' }
  };

  var LANG_ORDER = ['en-IE', 'da-DK', 'cs-CZ', 'el-GR'];

  var langSwitcherInstances = [];

  var getHreflangAlternates = function () {
    var map = {};
    document.querySelectorAll('link[rel="alternate"][hreflang]').forEach(function (link) {
      var lang = link.getAttribute('hreflang');
      var href = link.getAttribute('href');
      if (!lang || !href || lang === 'x-default') {
        return;
      }
      map[lang] = href;
    });
    return map;
  };

  var detectCurrentLocale = function (alternates) {
    var htmlLang = document.documentElement.lang;
    if (htmlLang && alternates[htmlLang]) {
      return htmlLang;
    }
    var canonical = document.querySelector('link[rel="canonical"]');
    if (canonical) {
      var canUrl = canonical.getAttribute('href');
      var lang;
      for (lang in alternates) {
        if (alternates[lang] === canUrl) {
          return lang;
        }
      }
    }
    return 'en-IE';
  };

  var getLocaleMeta = function (lang) {
    return LOCALE_META[lang] || {
      code: lang.split('-')[1] || lang.slice(0, 2).toUpperCase(),
      label: lang,
      flag: 'ie'
    };
  };

  // инлайн-SVG флагов: не зависят от путей и всегда рендерятся в макете
  var FLAG_SVG = {
    'ie': '<svg class="lang-switcher__flag" width="22" height="16" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 40" role="img" aria-hidden="true"><rect width="20" height="40" fill="#169b62"/><rect x="20" width="20" height="40" fill="#ffffff"/><rect x="40" width="20" height="40" fill="#ff883e"/></svg>',
    'cz': '<svg class="lang-switcher__flag" width="22" height="16" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 40" role="img" aria-hidden="true"><rect width="60" height="20" fill="#ffffff"/><rect y="20" width="60" height="20" fill="#d7141a"/><path d="M0 0 L30 20 L0 40 Z" fill="#11457e"/></svg>',
    'dk': '<svg class="lang-switcher__flag" width="22" height="16" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 40" role="img" aria-hidden="true"><rect width="60" height="40" fill="#c8102e"/><rect x="16" width="8" height="40" fill="#ffffff"/><rect y="16" width="60" height="8" fill="#ffffff"/></svg>',
    'gr': '<svg class="lang-switcher__flag" width="22" height="16" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 40" role="img" aria-hidden="true"><rect width="60" height="40" fill="#0d5eaf"/><g fill="#ffffff"><rect y="4.44" width="60" height="3.7"/><rect y="12.59" width="60" height="3.7"/><rect y="20.74" width="60" height="3.7"/><rect y="28.89" width="60" height="3.7"/><rect x="0" y="0" width="20" height="20.74" fill="#0d5eaf"/><rect x="8.15" width="3.7" height="20.74"/><rect y="8.52" width="20" height="3.7"/></g></svg>'
  };
  var flagMarkup = function (flagCode) {
    return FLAG_SVG[flagCode] || FLAG_SVG['ie'] || '';
  };

  var chevronSvg = '<svg class="lang-switcher__chevron" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  var buildLangSwitcherMarkup = function (alternates, currentLocale, variant) {
    var currentMeta = getLocaleMeta(currentLocale);
    var listItems = LANG_ORDER.filter(function (lang) {
      return alternates[lang];
    }).map(function (lang) {
      var meta = getLocaleMeta(lang);
      var isActive = lang === currentLocale;
      return '<li role="none">' +
        '<a class="lang-switcher__item' + (isActive ? ' is-active' : '') + '" href="' + alternates[lang] + '" role="option" aria-selected="' + (isActive ? 'true' : 'false') + '" data-lang="' + lang + '" hreflang="' + lang + '">' +
        flagMarkup(meta.flag) +
        '<span class="lang-switcher__label">' + meta.label + '</span>' +
        '</a></li>';
    }).join('');

    return '<div class="lang-switcher' + (variant === 'drawer' ? ' lang-switcher--drawer' : '') + '" data-variant="' + variant + '">' +
      '<button type="button" class="lang-switcher__toggle" aria-expanded="false" aria-haspopup="listbox" aria-label="Select language">' +
      flagMarkup(currentMeta.flag) +
      '<span class="lang-switcher__code">' + currentMeta.code + '</span>' +
      chevronSvg +
      '</button>' +
      '<div class="lang-switcher__panel" role="listbox" aria-label="Languages">' +
      '<ul class="lang-switcher__list">' + listItems + '</ul>' +
      '</div></div>';
  };

  var closeAllLangSwitchers = function (except) {
    langSwitcherInstances.forEach(function (instance) {
      if (except && instance.root === except) {
        return;
      }
      instance.close();
    });
  };

  var bindLangSwitcher = function (root) {
    var toggle = root.querySelector('.lang-switcher__toggle');
    var panel = root.querySelector('.lang-switcher__panel');
    if (!toggle || !panel) {
      return null;
    }

    var instance = {
      root: root,
      close: function () {
        root.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      },
      open: function () {
        closeAllLangSwitchers(root);
        root.classList.add('is-open');
        toggle.setAttribute('aria-expanded', 'true');
      }
    };

    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      if (root.classList.contains('is-open')) {
        instance.close();
      } else {
        instance.open();
      }
    });

    root.querySelectorAll('.lang-switcher__item').forEach(function (item) {
      item.addEventListener('click', function () {
        var lang = item.getAttribute('data-lang');
        if (lang) {
          try {
            localStorage.setItem(LANG_STORAGE_KEY, lang);
          } catch (err) {
            /* ignore storage errors */
          }
        }
        if (root.classList.contains('lang-switcher--drawer')) {
          setDrawerOpen(false);
        }
      });
    });

    langSwitcherInstances.push(instance);
    return instance;
  };

  var initLangSwitcher = function () {
    var alternates = getHreflangAlternates();
    var available = LANG_ORDER.filter(function (lang) {
      return alternates[lang];
    });
    if (available.length < 2) {
      return;
    }

    var currentLocale = detectCurrentLocale(alternates);
    var headerActions = document.querySelector('.header__actions');
    if (headerActions) {
      headerActions.insertAdjacentHTML('afterbegin', buildLangSwitcherMarkup(alternates, currentLocale, 'header'));
      bindLangSwitcher(headerActions.querySelector('.lang-switcher'));
    }

    var drawerBody = document.querySelector('.drawer__body');
    if (drawerBody) {
      var registerBtn = drawerBody.querySelector('[data-auth="register"]');
      var drawerMarkup = buildLangSwitcherMarkup(alternates, currentLocale, 'drawer');
      if (registerBtn) {
        registerBtn.insertAdjacentHTML('beforebegin', drawerMarkup);
      } else {
        drawerBody.insertAdjacentHTML('beforeend', drawerMarkup);
      }
      bindLangSwitcher(drawerBody.querySelector('.lang-switcher--drawer'));
    }
  };

  document.addEventListener('click', function (e) {
    if (!e.target.closest('.lang-switcher')) {
      closeAllLangSwitchers();
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeAllLangSwitchers();
      closeAuth();
      setDrawerOpen(false);
    }
  });

  initLangSwitcher();

  document.querySelectorAll('.header__nav a[href^="#"], .footer a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      var href = this.getAttribute('href');
      if (!href || href === '#' || !href.startsWith('#')) {
        return;
      }
      var id = href.slice(1);
      if (!id) {
        return;
      }
      var target = document.getElementById(id);
      if (!target) {
        return;
      }
      e.preventDefault();
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    });
  });

  document.querySelectorAll('form[action="#"]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      openPartnerOffer();
    });
  });

  if (authModal) {
    var authForm = authModal.querySelector('form');
    if (authForm) {
      authForm.addEventListener('submit', function (event) {
        event.preventDefault();
        openPartnerOffer();
      });
    }
  }
})();
