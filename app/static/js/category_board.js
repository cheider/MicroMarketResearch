(function () {
    const dropzones = document.querySelectorAll('.board-dropzone');
    if (!dropzones.length || typeof Sortable === 'undefined') return;

    let saveTimer = null;
    let dragging = false;
    let activeColumn = null;

    function pointerFromEvent(e) {
        if (!e) return null;
        if (e.clientX != null && e.clientY != null) {
            return { x: e.clientX, y: e.clientY };
        }
        const touch = e.changedTouches && e.changedTouches[0];
        if (touch) return { x: touch.clientX, y: touch.clientY };
        return null;
    }

    function columnAtPointer(x, y) {
        const elements = document.elementsFromPoint(x, y);
        for (let i = 0; i < elements.length; i += 1) {
            const el = elements[i];
            if (el.classList && (
                el.classList.contains('sortable-ghost') ||
                el.classList.contains('sortable-drag')
            )) {
                continue;
            }
            const col = el.closest && el.closest('.board-column');
            if (col) return col;
        }
        return null;
    }

    function setActiveColumn(col) {
        if (activeColumn === col) return;
        if (activeColumn) activeColumn.classList.remove('is-drop-target');
        activeColumn = col;
        if (activeColumn) activeColumn.classList.add('is-drop-target');
    }

    function collectAssignments() {
        const assignments = [];
        document.querySelectorAll('.board-column').forEach(function (col) {
            const categoryId = col.dataset.categoryId || null;
            const slug = categoryId === '' ? null : categoryId;
            col.querySelectorAll('.board-chip').forEach(function (chip, idx) {
                assignments.push({
                    item_id: chip.dataset.itemId,
                    product_category_id: slug,
                    sort: idx,
                });
            });
        });
        return assignments;
    }

    function showToast(el, message) {
        el.textContent = message;
        el.style.display = 'block';
        setTimeout(function () { el.style.display = 'none'; }, 2500);
    }

    function scheduleSave() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
            fetch('/api/inventory-tools/categorization', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ assignments: collectAssignments() }),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (res) {
                    if (res.data.errors && res.data.errors.length) {
                        showToast(
                            document.getElementById('errorToast'),
                            'Save error: ' + res.data.errors[0].error
                        );
                    } else {
                        showToast(document.getElementById('saveToast'), 'Saved');
                    }
                })
                .catch(function () {
                    showToast(document.getElementById('errorToast'), 'Save failed');
                });
        }, 400);
    }

    function markScrollableDropzones() {
        dropzones.forEach(function (zone) {
            const overflows = zone.scrollHeight > zone.clientHeight + 2;
            zone.classList.toggle('is-scrollable', overflows);
        });
    }

    function snapChipToColumnUnderPointer(chip, e) {
        const pt = pointerFromEvent(e);
        if (!pt) return;
        const col = columnAtPointer(pt.x, pt.y);
        if (!col) return;
        const zone = col.querySelector('.board-dropzone');
        if (!zone || zone === chip.parentElement) return;
        zone.appendChild(chip);
    }

    document.querySelectorAll('.board-chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            if (dragging) return;
            const href = chip.dataset.href;
            if (href) window.location.href = href;
        });
    });

    function trackPointerWhileDragging(e) {
        if (!dragging) return;
        const pt = pointerFromEvent(e);
        if (!pt) return;
        setActiveColumn(columnAtPointer(pt.x, pt.y));
    }

    document.addEventListener('mousemove', trackPointerWhileDragging);
    document.addEventListener('touchmove', trackPointerWhileDragging, { passive: true });

    dropzones.forEach(function (zone) {
        Sortable.create(zone, {
            group: 'categories',
            animation: 120,
            draggable: '.board-chip',
            direction: 'vertical',
            emptyInsertThreshold: 9999,
            swapThreshold: 0.5,
            invertSwap: false,
            fallbackOnBody: true,
            scroll: true,
            bubbleScroll: true,
            scrollSensitivity: 64,
            scrollSpeed: 14,
            onStart: function () {
                dragging = true;
            },
            onMove: function (evt, originalEvent) {
                const pt = pointerFromEvent(originalEvent);
                if (!pt) return true;
                const intendedCol = columnAtPointer(pt.x, pt.y);
                if (!intendedCol) return false;
                const intendedZone = intendedCol.querySelector('.board-dropzone');
                return intendedZone === evt.to;
            },
            onEnd: function (evt) {
                dragging = false;
                setActiveColumn(null);
                snapChipToColumnUnderPointer(evt.item, evt.originalEvent);
                scheduleSave();
                markScrollableDropzones();
            },
            onChoose: function () {
                dragging = true;
            },
            onUnchoose: function () {
                dragging = false;
                setActiveColumn(null);
            },
        });
    });

    markScrollableDropzones();
    window.addEventListener('resize', markScrollableDropzones);

    const previewBtn = document.getElementById('btnPreviewRules');
    const applyBtn = document.getElementById('btnApplyRules');
    const applySuggestionsBtn = document.getElementById('btnApplySuggestions');
    const previewModal = document.getElementById('previewModal');

    if (applySuggestionsBtn) {
        applySuggestionsBtn.addEventListener('click', function () {
            if (!confirm('Move unassigned items into their suggested categories?')) return;
            fetch('/api/inventory-tools/apply-suggestions', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    alert('Applied ' + (data.updated || 0) + ' suggestion(s). Reloading.');
                    window.location.reload();
                })
                .catch(function () {
                    showToast(document.getElementById('errorToast'), 'Apply suggestions failed');
                });
        });
    }

    if (previewBtn) {
        previewBtn.addEventListener('click', function () {
            fetch('/api/inventory-tools/auto-categorize/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ only_unassigned: true }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    const tbody = document.querySelector('#previewTable tbody');
                    const empty = document.getElementById('previewEmpty');
                    tbody.innerHTML = '';
                    if (!data.preview || !data.preview.length) {
                        empty.style.display = 'block';
                    } else {
                        empty.style.display = 'none';
                        data.preview.forEach(function (row) {
                            const tr = document.createElement('tr');
                            tr.innerHTML =
                                '<td>' + row.name + '</td>' +
                                '<td>' + (row.current || '—') + '</td>' +
                                '<td>' + row.suggested + '</td>' +
                                '<td class="text-muted small">' + row.rule_matched + '</td>';
                            tbody.appendChild(tr);
                        });
                    }
                    if (typeof bootstrap !== 'undefined') {
                        new bootstrap.Modal(previewModal).show();
                    }
                });
        });
    }

    if (applyBtn) {
        applyBtn.addEventListener('click', function () {
            if (!confirm('Apply auto-rules to uncategorized, non-manual items?')) return;
            fetch('/api/inventory-tools/auto-categorize/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ only_unassigned: true, write_as_suggested: false }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    alert('Updated ' + (data.updated || 0) + ' item(s). Reloading.');
                    window.location.reload();
                });
        });
    }
})();
