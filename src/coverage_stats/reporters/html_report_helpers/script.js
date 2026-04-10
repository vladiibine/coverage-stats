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

function toggleTestIdOverflow(link) {
    var td = link.closest('td');
    var overflow = td.querySelector('.test-id-overflow');
    var showMore = td.querySelector('.test-id-show-more');
    var showLess = td.querySelector('.test-id-show-less');
    var expanding = overflow.style.display === 'none';
    overflow.style.display = expanding ? '' : 'none';
    showMore.style.display = expanding ? 'none' : '';
    showLess.style.display = expanding ? '' : 'none';
}

// Column sorting — sortable table with folder-tree awareness
class TableSorter {
    constructor(tableId) {
        this._tableId = tableId;
        this._currentCol = null;
        this._currentDir = null;
        this._tbody = null;
        this._headers = {};
    }

    init() {
        var table = document.getElementById(this._tableId);
        if (!table) { return; }
        this._tbody = table.querySelector('tbody');
        var self = this;
        table.querySelectorAll('th.sortable').forEach(function(th) {
            self._headers[th.dataset.col] = th;
        });
    }

    handleClick(th) {
        var col = th.dataset.col;
        if (this._currentCol === col) {
            if (this._currentDir === 'asc') {
                this._setSort(col, 'desc');
            } else {
                this._clearSort();
            }
        } else {
            this._setSort(col, 'asc');
        }
    }

    _setSort(col, dir) {
        this._clearIndicators();
        this._currentCol = col;
        this._currentDir = dir;
        var th = this._headers[col];
        if (th) { th.classList.add('sort-' + dir); }
        this._applySort();
    }

    _clearSort() {
        this._clearIndicators();
        this._currentCol = null;
        this._currentDir = null;
        this._restoreOriginal();
    }

    _clearIndicators() {
        var headers = this._headers;
        Object.keys(headers).forEach(function(col) {
            headers[col].classList.remove('sort-asc', 'sort-desc');
        });
    }

    _applySort() {
        var rows = Array.from(this._tbody.querySelectorAll('tr'));
        var tree = this._buildTree(rows);
        this._sortTree(tree, this._currentCol, this._currentDir);
        var sorted = this._flattenTree(tree);
        var tbody = this._tbody;
        sorted.forEach(function(row) { tbody.appendChild(row); });
    }

    _restoreOriginal() {
        var rows = Array.from(this._tbody.querySelectorAll('tr'));
        rows.sort(function(a, b) {
            return parseInt(a.dataset.originalIndex) - parseInt(b.dataset.originalIndex);
        });
        var tbody = this._tbody;
        rows.forEach(function(row) { tbody.appendChild(row); });
    }

    _buildTree(rows) {
        var tree = {};
        rows.forEach(function(row) {
            var parent = row.dataset.parent !== undefined ? row.dataset.parent : '';
            if (!tree[parent]) { tree[parent] = []; }
            tree[parent].push(row);
        });
        return tree;
    }

    _sortTree(tree, col, dir) {
        var comparator = this._makeComparator(col, dir);
        Object.keys(tree).forEach(function(parent) {
            tree[parent].sort(comparator);
        });
    }

    _makeComparator(col, dir) {
        var self = this;
        var mult = dir === 'asc' ? 1 : -1;
        return function(a, b) {
            var av = self._getSortValue(a, col);
            var bv = self._getSortValue(b, col);
            if (av < bv) { return -mult; }
            if (av > bv) { return mult; }
            return 0;
        };
    }

    _colToDataKey(col) {
        var camel = col.replace(/-([a-z])/g, function(_, c) { return c.toUpperCase(); });
        return 'sort' + camel.charAt(0).toUpperCase() + camel.slice(1);
    }

    _getSortValue(row, col) {
        var key = this._colToDataKey(col);
        var val = row.dataset[key];
        if (val === undefined || val === '') { return ''; }
        var num = parseFloat(val);
        return isNaN(num) ? val.toLowerCase() : num;
    }

    _flattenTree(tree) {
        var result = [];
        this._flattenNode(result, '', tree);
        return result;
    }

    _flattenNode(result, parentId, tree) {
        var self = this;
        var children = tree[parentId] || [];
        children.forEach(function(row) {
            result.push(row);
            var rowId = row.id;
            if (rowId && tree[rowId]) {
                self._flattenNode(result, rowId, tree);
            }
        });
    }
}

var tableSorter = new TableSorter('coverage-table');
document.addEventListener('DOMContentLoaded', function() { tableSorter.init(); });

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
