"""Lazy two-level tree model (groups -> files). Handles very large result sets.

Column 0 is the "Remove" checkbox column:
  * file rows:  ticked = marked for REMOVE, unticked = KEEP
  * group rows: ticked = every duplicate in the group is marked (one copy is
    always kept), partial = some are marked, unticked = nothing marked.
"""

import os
import time

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from ..i18n import human_size, tr

COLS = ["col_remove", "col_name", "col_match", "col_res", "col_size", "col_date", "col_fmt", "col_folder"]
C_REMOVE, C_NAME, C_MATCH, C_RES, C_SIZE, C_DATE, C_FMT, C_FOLDER = range(8)


def date_text(mtime_ns):
    """File modified time as local 'YYYY-MM-DD HH:MM'."""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(mtime_ns) / 1e9))
    except (OSError, OverflowError, ValueError):
        return ""
KEEP_COLOR = QColor(46, 160, 67)
REMOVE_COLOR = QColor(207, 34, 46)
VARIANT_COLOR = QColor(150, 110, 230)    # numbered variants (kept, not duplicates)


def kind_text(m):
    if m.kind == "keep":
        return tr("kind_keep")
    if m.kind == "exact":
        return tr("kind_exact")
    if m.kind == "variant":
        r = getattr(m, "reason", "")
        if r.startswith("prefix:"):
            return tr("kind_exc_prefix", n=r.split(":", 1)[1])
        return tr("kind_exc_pattern")
    return tr("kind_" + m.kind, p=int(round(m.score * 100)))


class GroupModel(QAbstractItemModel):
    marksChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groups = []
        self.ft = None
        self.n_marked = 0
        self.bytes_marked = 0
        self._bold = QFont()
        self._bold.setBold(True)
        self.sort_key = None      # (column, Qt.SortOrder) chosen by clicking a header

    # ----- data management -----
    def set_result(self, result):
        self.beginResetModel()
        self.ft = result.files if result else None
        self.groups = list(result.groups) if result else []
        if self.sort_key and self.groups:
            self._sort_lists(*self.sort_key)
        self.endResetModel()
        self._recount()

    # ----- sorting -----
    def _member_key(self, col, m):
        ft, i = self.ft, m.idx
        if col == C_NAME:
            return os.path.basename(ft.paths[i]).casefold()
        if col == C_MATCH:
            return (m.score, m.kind)
        if col == C_RES:
            return int(ft.w[i]) * int(ft.h[i])
        if col == C_SIZE:
            return int(ft.size[i])
        if col == C_DATE:
            return int(ft.mtime[i])
        if col == C_FMT:
            return ft.fmt[i]
        return os.path.dirname(ft.paths[i]).casefold()

    def _group_key(self, col, g):
        """A group sorts by its best file, except Match (its weakest match) and
        Size (space it frees, as shown on the group row; then its largest file)."""
        ft = self.ft
        if col == C_MATCH:
            return min((m.score for m in g.members[1:]), default=1.0)
        if col == C_SIZE:
            return (sum(int(ft.size[m.idx]) for m in g.members if m.remove),
                    max(int(ft.size[m.idx]) for m in g.members))
        return self._member_key(col, g.members[0])

    def _sort_lists(self, col, order):
        desc = order == Qt.SortOrder.DescendingOrder
        for g in self.groups:     # the best copy (row 0) stays first: it is the default keeper
            if len(g.members) > 2:
                g.members[1:] = sorted(g.members[1:], key=lambda m: self._member_key(col, m), reverse=desc)
        self.groups.sort(key=lambda g: self._group_key(col, g), reverse=desc)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if column == C_REMOVE or not 0 <= column < len(COLS):
            return
        self.sort_key = (column, order)
        if not self.groups or self.ft is None:
            return
        # keep expanded groups and the selection: remember what each persistent index points to
        self.layoutAboutToBeChanged.emit()
        old = self.persistentIndexList()
        refs = []
        for idx in old:
            gi, mi = self.member_at(idx)
            g = self.groups[gi]
            refs.append((g, g.members[mi] if mi is not None else None, idx.column()))
        self._sort_lists(column, order)
        gpos = {id(g): k for k, g in enumerate(self.groups)}
        new = []
        for g, m, col in refs:
            gi = gpos[id(g)]
            if m is None:
                new.append(self.createIndex(gi, col, 0))
            else:
                new.append(self.createIndex(next(k for k, x in enumerate(g.members) if x is m), col, gi + 1))
        self.changePersistentIndexList(old, new)
        self.layoutChanged.emit()

    def _recount(self):
        n = b = 0
        for g in self.groups:
            for m in g.members:
                if m.remove:
                    n += 1
                    b += int(self.ft.size[m.idx])
        self.n_marked, self.bytes_marked = n, b
        self.marksChanged.emit()

    def _emit_group(self, gi):
        gidx = self.index(gi, 0)
        last = len(COLS) - 1
        n = len(self.groups[gi].members)
        if n:
            self.dataChanged.emit(self.index(0, 0, gidx), self.index(n - 1, last, gidx))
        self.dataChanged.emit(gidx, self.index(gi, last))

    def _set(self, m, remove):
        """Change one member without emitting; returns True if it changed."""
        if m.remove == remove:
            return False
        m.remove = remove
        sz = int(self.ft.size[m.idx])
        self.n_marked += 1 if remove else -1
        self.bytes_marked += sz if remove else -sz
        return True

    def set_remove(self, gi, mi, remove):
        if self._set(self.groups[gi].members[mi], remove):
            self._emit_group(gi)
            self.marksChanged.emit()

    def keep_only(self, gi, mi):
        for k, m in enumerate(self.groups[gi].members):
            self._set(m, k != mi)
        self._emit_group(gi)
        self.marksChanged.emit()

    def keeper_row(self, gi):
        """The file kept in a group: the first unmarked one, else the best (row 0)."""
        for k, m in enumerate(self.groups[gi].members):
            if not m.remove:
                return k
        return 0

    def group_state(self, gi):
        g = self.groups[gi]
        n = sum(1 for m in g.members if m.remove)
        if n == 0:
            return Qt.CheckState.Unchecked
        if n >= len(g.members) - 1:
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked

    def set_group(self, gi, mark):
        """mark=True: mark every duplicate (keep one copy); False: unmark all."""
        keep = self.keeper_row(gi)
        for k, m in enumerate(self.groups[gi].members):
            self._set(m, mark and k != keep)
        self._emit_group(gi)
        self.marksChanged.emit()

    def select_kinds(self, kinds):
        """Mark only duplicates whose match type is in kinds; keep the best copy."""
        for g in self.groups:
            for k, m in enumerate(g.members):
                m.remove = k != 0 and m.kind in kinds
        self._refresh_all()

    def mark_all(self):
        """Tick every file, including the ones that would be kept."""
        for g in self.groups:
            for m in g.members:
                m.remove = True
        self._refresh_all()

    def total_files(self):
        return sum(len(g.members) for g in self.groups)

    def reapply_variants(self, patterns, prefix_len=0):
        """Re-run the variant rules on the current results (resets marks)."""
        from ..variants import apply_variants
        if not self.ft:
            return
        self.beginResetModel()
        self.groups = apply_variants(self.groups, self.ft, patterns, prefix_len)
        if self.sort_key:
            self._sort_lists(*self.sort_key)
        self.endResetModel()
        self._recount()

    def auto_select(self):
        self.select_kinds({"exact", "similar", "cropped"})

    def unmark_all(self):
        for g in self.groups:
            for m in g.members:
                m.remove = False
        self._refresh_all()

    def invert(self):
        """Swap keep/remove in every group; a group never ends up fully marked."""
        for g in self.groups:
            for m in g.members:
                m.remove = not m.remove
            if all(m.remove for m in g.members):
                g.members[0].remove = False
        self._refresh_all()

    def _refresh_all(self):
        if self.groups:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.groups) - 1, len(COLS) - 1))
            for gi in range(len(self.groups)):
                n = len(self.groups[gi].members)
                gidx = self.index(gi, 0)
                self.dataChanged.emit(self.index(0, 0, gidx), self.index(n - 1, len(COLS) - 1, gidx))
        self._recount()

    def marked(self, allow_full=False):
        """[(group, member)] marked for removal. Groups where *all* files are marked
        are skipped (so one copy always survives) unless allow_full (used for Move,
        which loses nothing)."""
        out, skipped = [], 0
        for g in self.groups:
            marks = [m for m in g.members if m.remove]
            if not marks:
                continue
            if len(marks) == len(g.members) and not allow_full:
                skipped += 1
                continue
            out.extend((g, m) for m in marks)
        return out, skipped

    def add_groups(self, groups):
        """Append groups (e.g. unhidden ones), keeping the chosen sort order."""
        self.beginResetModel()
        self.groups.extend(groups)
        if self.sort_key:
            self._sort_lists(*self.sort_key)
        self.endResetModel()
        self._recount()

    def remove_groups(self, groups):
        drop = {id(g) for g in groups}
        self.beginResetModel()
        self.groups = [g for g in self.groups if id(g) not in drop]
        self.endResetModel()
        self._recount()

    def remove_done(self, done_idx):
        """Drop processed files; drop groups that no longer have duplicates."""
        self.beginResetModel()
        new = []
        for g in self.groups:
            g.members = [m for m in g.members if m.idx not in done_idx]
            if len(g.members) >= 2:
                new.append(g)
        self.groups = new
        self.endResetModel()
        self._recount()

    def retranslate(self):
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(COLS) - 1)
        self._refresh_all()

    def member_at(self, index):
        """(group_row, member_row or None) for an index."""
        if not index.isValid():
            return None, None
        gid = index.internalId()
        if gid == 0:
            return index.row(), None
        return gid - 1, index.row()

    # ----- Qt model API -----
    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        gid = index.internalId()
        if gid == 0:
            return QModelIndex()
        return self.createIndex(gid - 1, 0, 0)

    def rowCount(self, parent=QModelIndex()):
        if not parent.isValid():
            return len(self.groups)
        if parent.internalId() == 0 and parent.column() == 0:
            return len(self.groups[parent.row()].members)
        return 0

    def columnCount(self, parent=QModelIndex()):
        return len(COLS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            if section == C_REMOVE:   # room on the left for the Select checkbox
                return "       " + tr("col_select")
            return tr(COLS[section])
        if role == Qt.ItemDataRole.ToolTipRole and section == C_REMOVE:
            return tr("all_tip")
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == C_REMOVE:
            f |= Qt.ItemFlag.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.ft is None:
            return None
        ft = self.ft
        col = index.column()
        gi, mi = self.member_at(index)
        g = self.groups[gi]
        if mi is None:  # group row
            if role == Qt.ItemDataRole.CheckStateRole and col == C_REMOVE:
                return self.group_state(gi)
            if role == Qt.ItemDataRole.DisplayRole:
                if col == C_NAME:
                    return tr("group_n", n=gi + 1, count=len(g.members))
                if col == C_MATCH:
                    kinds = {m.kind for m in g.members[1:]}
                    return kind_text(g.members[1]) + (" …" if len(kinds) > 1 else "") if len(g.members) > 1 else ""
                if col == C_SIZE:
                    b = sum(int(ft.size[m.idx]) for m in g.members if m.remove)
                    return tr("reclaim", size=human_size(b))
            if role == Qt.ItemDataRole.ToolTipRole and col == C_REMOVE:
                return tr("group_tip")
            if role == Qt.ItemDataRole.FontRole:
                return self._bold
            return None

        m = g.members[mi]
        i = m.idx
        path = ft.paths[i]
        if role == Qt.ItemDataRole.DisplayRole:
            if col == C_REMOVE:
                return tr("tag_remove") if m.remove else tr("tag_keep")
            if col == C_NAME:
                return os.path.basename(path)
            if col == C_MATCH:
                return kind_text(m)
            if col == C_RES:
                return f"{ft.w[i]} × {ft.h[i]}"
            if col == C_SIZE:
                return human_size(ft.size[i])
            if col == C_DATE:
                return date_text(ft.mtime[i])
            if col == C_FMT:
                return ft.fmt[i]
            if col == C_FOLDER:
                return os.path.dirname(path)
        elif role == Qt.ItemDataRole.CheckStateRole and col == C_REMOVE:
            return Qt.CheckState.Checked if m.remove else Qt.CheckState.Unchecked
        elif role == Qt.ItemDataRole.ForegroundRole and col in (C_REMOVE, C_NAME, C_MATCH):
            if m.remove:
                return QBrush(REMOVE_COLOR)
            return QBrush(VARIANT_COLOR if m.kind == "variant" and col == C_MATCH else KEEP_COLOR)
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == C_REMOVE:
                return tr("remove_tip")
            return f"{path}\n{tr('tag_remove') if m.remove else tr('tag_keep')}"
        elif role == Qt.ItemDataRole.FontRole and (mi == 0 or col == C_REMOVE):
            return self._bold
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.CheckStateRole or index.column() != C_REMOVE:
            return False
        gi, mi = self.member_at(index)
        checked = Qt.CheckState(value) == Qt.CheckState.Checked
        if mi is None:
            # Clicking a partial group marks all its duplicates.
            self.set_group(gi, self.group_state(gi) != Qt.CheckState.Checked)
        else:
            self.set_remove(gi, mi, checked)
        return True
