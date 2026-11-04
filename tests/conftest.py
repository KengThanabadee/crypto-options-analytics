import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def smile_boxes(app):
    """The IV smile expiry checkboxes, in expiry order."""
    return [box for box in app.checkbox if box.key.startswith("smile_expiry_")]


def oi_boxes(app):
    """The OI expiry checkboxes, in expiry order."""
    return [box for box in app.checkbox if box.key.startswith("oi_expiry_")]


def oi_expiries(app):
    """The ticked OI expiries as taus; empty means All expiries."""
    return [float(box.key.rsplit("_", 1)[1]) for box in oi_boxes(app) if box.value]


def set_oi_expiries(app, taus):
    """Tick exactly ``taus`` in the OI expiry picker and rerun."""
    chosen = {float(tau) for tau in taus}
    for box in oi_boxes(app):
        box.set_value(float(box.key.rsplit("_", 1)[1]) in chosen)
    return app.run()
