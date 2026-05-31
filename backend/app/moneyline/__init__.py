"""Form-based moneyline model.

Win probability comes ONLY from our SportRadar data — last-5 results, margins,
points-allowed floor, home/away record, rest, and a pace proxy — never a black
box. (We deliberately do NOT use any pre-trained model whose feature schema we
can't reproduce from SportRadar.)
"""

from app.moneyline.form import TeamForm, build_form, predict_moneyline

__all__ = ["TeamForm", "build_form", "predict_moneyline"]
