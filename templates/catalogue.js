(function () {
  'use strict';
  var dataEl = document.getElementById('catalogue-data');
  var input = document.getElementById('q');
  if (!dataEl || !input) return;

  var items = JSON.parse(dataEl.textContent);
  var norm = function (s) { return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); };
  items.forEach(function (it) {
    it.hay = norm(it.text);
    it.card = document.querySelector('.card[data-slug="' + it.slug + '"]');
  });

  var boxes = Array.prototype.slice.call(document.querySelectorAll('.facet input[type=checkbox]'));
  var countEl = document.getElementById('count');
  var noneEl = document.getElementById('none');
  var clearBtns = [document.getElementById('clear'), document.getElementById('clear2')].filter(Boolean);
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));

  function selected() {
    var sel = {};
    boxes.forEach(function (b) { if (b.checked) (sel[b.name] = sel[b.name] || []).push(b.value); });
    return sel;
  }

  // An item matches when every search term appears, and, for each facet with ticked values,
  // it has at least one of them (OR inside a facet, AND across facets). `skip` ignores one facet,
  // which gives the counts shown next to that facet's own options.
  function matches(it, terms, sel, skip) {
    for (var i = 0; i < terms.length; i++) if (it.hay.indexOf(terms[i]) === -1) return false;
    for (var k in sel) {
      if (k === skip) continue;
      var have = it.facets[k] || [];
      if (!sel[k].some(function (v) { return have.indexOf(v) !== -1; })) return false;
    }
    return true;
  }

  function update(writeUrl) {
    var q = input.value.trim();
    var terms = norm(q).split(/\s+/).filter(Boolean);
    var sel = selected();
    var shown = 0;
    items.forEach(function (it) {
      var ok = matches(it, terms, sel);
      if (it.card) it.card.hidden = !ok;
      if (ok) shown++;
    });
    boxes.forEach(function (b) {
      var n = items.filter(function (it) {
        return (it.facets[b.name] || []).indexOf(b.value) !== -1 && matches(it, terms, sel, b.name);
      }).length;
      var c = b.parentNode.querySelector('[data-count]');
      if (c) c.textContent = n;
      b.disabled = n === 0 && !b.checked;
      b.parentNode.classList.toggle('off', b.disabled);
    });
    countEl.textContent = shown + (shown === 1 ? ' resource' : ' resources') +
      (q || Object.keys(sel).length ? ' match' + (shown === 1 ? 'es' : '') : '');
    noneEl.hidden = shown !== 0;
    var active = !!q || Object.keys(sel).length > 0;
    clearBtns.forEach(function (b) { b.hidden = !active && b.id === 'clear'; });

    var params = new URLSearchParams();
    if (q) params.set('q', q);
    Object.keys(sel).forEach(function (k) { sel[k].forEach(function (v) { params.append(k, v); }); });
    var qs = params.toString();
    if (writeUrl) {
      try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '')); } catch (e) { /* ignore */ }
    }
    // Carry the search and filters across theme tabs.
    tabs.forEach(function (t) {
      var base = t.getAttribute('href').split('?')[0];
      t.setAttribute('href', base + (qs ? '?' + qs : ''));
    });
  }

  // Restore state from the address, so a filtered view can be shared as a link.
  var start = new URLSearchParams(location.search);
  if (start.get('q')) input.value = start.get('q');
  boxes.forEach(function (b) { if (start.getAll(b.name).indexOf(b.value) !== -1) b.checked = true; });

  var timer;
  input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { update(true); }, 120); });
  boxes.forEach(function (b) { b.addEventListener('change', function () { update(true); }); });
  clearBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      input.value = '';
      boxes.forEach(function (b) { b.checked = false; });
      update(true);
      input.focus();
    });
  });
  var fold = document.getElementById('facets');
  if (fold && window.matchMedia && window.matchMedia('(max-width: 820px)').matches && !Object.keys(selected()).length) fold.open = false;
  update(false);
})();
