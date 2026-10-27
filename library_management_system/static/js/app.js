(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var menu = $("#menuBtn"), side = $("#sidebar");
  if (menu && side) menu.addEventListener("click", function () { side.classList.toggle("open"); });

  // Live table filtering: <input data-filter="#tableId">
  $$("[data-filter]").forEach(function (input) {
    var table = $(input.dataset.filter);
    if (!table) return;
    input.addEventListener("input", function () {
      var q = input.value.toLowerCase().trim(), shown = 0;
      $$("tbody tr", table).forEach(function (tr) {
        var match = tr.textContent.toLowerCase().indexOf(q) !== -1;
        tr.hidden = !match;
        if (match) shown++;
      });
      var empty = $("#noMatch");
      if (empty) empty.hidden = shown > 0;
    });
  });

  // Confirmation dialogs: <form data-confirm="Are you sure?">
  $$("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.dataset.confirm)) e.preventDefault();
    });
  });

  // Issue form: show availability and due date preview
  var book = $("#book_id"), info = $("#bookInfo");
  if (book && info) {
    var showBook = function () {
      var o = book.options[book.selectedIndex];
      info.textContent = o && o.value
        ? o.dataset.available + " of " + o.dataset.total + " copies available · " + o.dataset.author : "";
    };
    book.addEventListener("change", showBook);
    showBook();
  }
  var days = $("#days"), due = $("#dueDate");
  if (days && due) {
    var showDue = function () {
      var n = parseInt(days.value, 10);
      if (n > 0) {
        var d = new Date();
        d.setDate(d.getDate() + n);
        due.textContent = d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
      } else { due.textContent = "—"; }
    };
    days.addEventListener("input", showDue);
    showDue();
  }

  // Dismiss flash messages
  $$(".flash button").forEach(function (b) {
    b.addEventListener("click", function () { b.parentElement.remove(); });
  });

  // Prevent double submits
  $$("form").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      setTimeout(function () {
        $$("button:not([type=button])", f).forEach(function (b) { b.disabled = true; });
      }, 0);
    });
  });
})();
