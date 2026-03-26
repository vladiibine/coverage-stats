function openHelp(id) {
    document.getElementById(id).style.display = 'flex';
}
function closeHelp(id) {
    document.getElementById(id).style.display = 'none';
}

function toggleFolder(id) {
    var row = document.getElementById(id);
    var toggle = row.querySelector('.toggle');
    var opening = toggle.textContent === '\u25b6';
    toggle.textContent = opening ? '\u25bc' : '\u25b6';
    var children = document.querySelectorAll('[data-parent="' + id + '"]');
    children.forEach(function(child) {
        child.style.display = opening ? '' : 'none';
        if (!opening) {
            var cid = child.id;
            if (cid) {
                var ct = child.querySelector('.toggle');
                if (ct && ct.textContent === '\u25bc') {
                    ct.textContent = '\u25b6';
                    hideDescendants(cid);
                }
            }
        }
    });
}
function hideDescendants(id) {
    document.querySelectorAll('[data-parent="' + id + '"]').forEach(function(row) {
        row.style.display = 'none';
        if (row.id) hideDescendants(row.id);
    });
}

// Column visibility — persisted in localStorage
(function() {
    var KEY = 'cov-stats-col-prefs';

    // Storage format: {col_id: bool} — only columns the user has explicitly toggled.
    // Columns absent from the object fall through to the Python-baked default.
    // Migration: old format was an array of hidden col ids.
    function loadExplicit() {
        try {
            var raw = localStorage.getItem(KEY);
            if (!raw) return {};
            var val = JSON.parse(raw);
            if (Array.isArray(val)) {
                // Migrate old hidden-set format
                var obj = {};
                val.forEach(function(col) { obj[col] = false; });
                return obj;
            }
            return val || {};
        } catch(e) { return {}; }
    }

    function saveExplicit(explicit) {
        try { localStorage.setItem(KEY, JSON.stringify(explicit)); } catch(e) {}
    }

    function applyCol(col, visible, animate) {
        var cells = document.querySelectorAll('[data-col="' + col + '"]');
        if (visible) {
            cells.forEach(function(el) {
                el.style.opacity = '0';
                el.classList.remove('col-hidden');
                if (animate) {
                    requestAnimationFrame(function() {
                        requestAnimationFrame(function() { el.style.opacity = ''; });
                    });
                } else {
                    el.style.opacity = '';
                }
            });
        } else {
            if (animate) {
                cells.forEach(function(el) { el.style.opacity = '0'; });
                setTimeout(function() {
                    cells.forEach(function(el) {
                        el.classList.add('col-hidden');
                        el.style.opacity = '';
                    });
                }, 220);
            } else {
                cells.forEach(function(el) { el.classList.add('col-hidden'); });
            }
        }
    }

    window.toggleCol = function(col, visible) {
        var explicit = loadExplicit();
        explicit[col] = visible;
        saveExplicit(explicit);
        applyCol(col, visible, true);
    };

    document.addEventListener('DOMContentLoaded', function() {
        var explicit = loadExplicit();
        document.querySelectorAll('.col-controls input[type="checkbox"]').forEach(function(cb) {
            var col = cb.value;
            if (col in explicit) {
                // User has explicitly toggled this column — honour their choice
                applyCol(col, explicit[col], false);
                cb.checked = explicit[col];
            } else {
                // No saved preference — use Python-baked default (col-hidden class)
                var firstCell = document.querySelector('[data-col="' + col + '"]');
                var visible = firstCell ? !firstCell.classList.contains('col-hidden') : true;
                cb.checked = visible;
            }
        });
    });
})();
