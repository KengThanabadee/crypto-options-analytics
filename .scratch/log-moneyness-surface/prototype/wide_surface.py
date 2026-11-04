"""PROTOTYPE, throwaway: compare 3D IV surfaces over Core vs wide moneyness."""
import sys
import numpy as np
from options_analytics import deribit, iv_source, visualization
from options_analytics.surface_transforms import interpolate_surface_2d

out = sys.argv[1]
c = deribit.parse_deribit_snapshot(deribit.load_deribit_snapshot("data/deribit_btc_options_snapshot.json"))
r = iv_source.build_iv_source_surface(c, "Exchange mark", bid_ask_iv=iv_source.solve_bid_ask_iv(c))
f = iv_source.iv_source_long_frame(r)
panels = []
for title, lo, hi, log in [
    ("A · Core K/S 0.8–1.2 (today)", 0.8, 1.2, False),
    ("B · Wide K/S 0.5–2.0", 0.5, 2.0, False),
    ("C · Wide 0.5–2.0 as ln(K/S)", 0.5, 2.0, True),
]:
    s = interpolate_surface_2d(f, min_moneyness=lo, max_moneyness=hi)
    if log:
        s = s.assign(moneyness=np.log(s["moneyness"]))
    fig = visualization.make_iv_surface_figure(s, iv_source="Exchange mark")
    fig.update_layout(template="plotly_dark", font_color="#c9ccd6", height=560,
                      title={"text": title, "x": 0.02})
    if log:
        fig.update_layout(scene_xaxis_title_text="ln(K / S)")
    panels.append(fig.to_html(full_html=False, include_plotlyjs="cdn" if not panels else False))
html = ("<html><head><meta charset='utf-8'><title>Wide surface prototype</title></head>"
        "<body style='background:#0e1117;margin:0'>" + "".join(
            f"<div id='p{i}' style='padding:8px 16px'>{p}</div>" for i, p in enumerate(panels)) + "</body></html>")
open(out, "w").write(html)
print("ok")
