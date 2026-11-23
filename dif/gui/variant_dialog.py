"""Exceptions window: two independent rules that keep look-alike files (not ticked).

Rule 1 - name patterns (comma-separated), e.g. *_p#  -> 12345678_p0 / 12345678_p1
Rule 2 - same first N characters of the name,      e.g. N=4 -> image_01 / image_02
Either rule is enough. Safety rules (identical files, same name) always win.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QScrollArea, QSpinBox, QVBoxLayout)

from ..i18n import tr
from ..variants import check_patterns, compile_patterns, explain, split_patterns


class VariantDialog(QDialog):
    def __init__(self, parent, patterns, patterns_on=True, prefix_on=False, prefix_len=8):
        super().__init__(parent)
        self.setWindowTitle(tr("var_title"))
        self.resize(780, 760)
        self.setMinimumSize(640, 660)
        lay = QVBoxLayout(self)

        help_lbl = QLabel(tr("var_help"))
        help_lbl.setWordWrap(True)
        help_lbl.setTextFormat(Qt.TextFormat.RichText)
        help_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()                       # never clipped: scrolls if the window is small
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(help_lbl)
        lay.addWidget(scroll, 1)

        # rule 1: name patterns
        self.cb_pat = QCheckBox(tr("var_rule1"))
        self.cb_pat.setChecked(patterns_on)
        lay.addWidget(self.cb_pat)
        self.edit = QLineEdit(", ".join(patterns))
        self.edit.setPlaceholderText(tr("var_placeholder"))
        f = self.edit.font()
        f.setFamily("Consolas")
        self.edit.setFont(f)
        lay.addWidget(self.edit)
        self.invalid = QLabel()
        self.invalid.setStyleSheet("color:#cf222e;")
        lay.addWidget(self.invalid)

        # rule 2: same beginning of name
        row = QHBoxLayout()
        self.cb_pre = QCheckBox(tr("var_rule2"))
        self.cb_pre.setChecked(prefix_on)
        self.sp_pre = QSpinBox()
        self.sp_pre.setRange(1, 200)
        self.sp_pre.setValue(int(prefix_len))
        row.addWidget(self.cb_pre)
        row.addWidget(self.sp_pre)
        row.addWidget(QLabel(tr("var_rule2_suffix")))
        row.addStretch()
        lay.addLayout(row)
        self.pre_hint = QLabel()
        self.pre_hint.setStyleSheet("color:gray;")
        lay.addWidget(self.pre_hint)

        # live tester
        test = QGridLayout()
        test.addWidget(QLabel(tr("var_test")), 0, 0, 1, 2)
        self.ta = QLineEdit("12345678_p0.png")
        self.tb = QLineEdit("12345678_p1.png")
        test.addWidget(self.ta, 1, 0)
        test.addWidget(self.tb, 1, 1)
        self.result = QLabel()
        test.addWidget(self.result, 2, 0, 1, 2)
        lay.addLayout(test)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        for sig in (self.edit.textChanged, self.ta.textChanged, self.tb.textChanged,
                    self.cb_pat.toggled, self.cb_pre.toggled, self.sp_pre.valueChanged):
            sig.connect(self._update)
        self._update()

    def patterns(self):
        return split_patterns(self.edit.text())

    def _update(self):
        self.edit.setEnabled(self.cb_pat.isChecked())
        self.sp_pre.setEnabled(self.cb_pre.isChecked())
        pats = self.patterns()
        bad = check_patterns(pats) if self.cb_pat.isChecked() else []
        self.invalid.setText(tr("var_invalid", lines=", ".join(bad)) if bad else "")
        n = self.sp_pre.value()
        sample = (self.ta.text() or "image_01")
        stem = sample.rsplit(".", 1)[0]
        self.pre_hint.setText(tr("var_rule2_hint", n=n, start=stem[:n]) if self.cb_pre.isChecked() else "")

        r = explain(self.ta.text(), self.tb.text(),
                    compile_patterns(pats if self.cb_pat.isChecked() else []),
                    n if self.cb_pre.isChecked() else 0)
        if r is None:
            text, color = tr("var_res_none"), "gray"
        elif r[0] == "safety":
            text, color = tr("var_res_safety"), "#cf222e"
        elif r[0] == "pattern":
            text, color = tr("var_res_pattern", p=r[1]), "#966ee6"
        else:
            text, color = tr("var_res_prefix", n=r[1]), "#966ee6"
        self.result.setText(text)
        self.result.setStyleSheet(f"color:{color}; font-weight:bold;")
