"""Capture the README dashboard images from the running app.

Start the dashboard on the checked-in snapshot first (no Fetch latest):

    python -m streamlit run app.py --server.headless true --server.port 8599

then run:

    python scripts/capture_readme_images.py --browser /path/to/chrome-headless-shell

The browser is any Chromium binary that supports --remote-debugging-port
(Chrome, Brave, or Playwright's chrome-headless-shell). The browser asks for
the dark colour scheme, which the page follows as its System theme. The page
opens at its defaults in a 1400 x 4000 viewport and each image is cropped from
the live DOM at 1.5x. The IV surface tab is captured as the Heatmap, then its
View control is switched to 3D for the surface image. The images are written to docs/images/ as JPEG. It needs the
`websockets` and `Pillow` packages, which the plain install brings.

To check a chart in the light theme, pass `--scheme light --out <dir>` with a
directory outside docs/images/; the script refuses docs/images/ there, so
the README images stay dark.

To check the IV surface in every state, pass `--states --out <dir>`: it saves
the IV surface tab for each moneyness range in Heatmap and 3D
(`surface-<range>-<view>.jpg`) instead of the README images. Run it once per
scheme. The browser takes a free debugging port, so captures from several
worktrees can run at once.

The 3D surface is WebGL. Headless Chromium draws it only with the software
renderer flags this script passes (`--use-angle=swiftshader
--enable-unsafe-swiftshader`); a headless browser started without them shows
an empty 3D frame.
"""
import argparse
import asyncio
import base64
import contextlib
import io
import itertools
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# Import this checkout's package, also from a worktree whose venv points elsewhere.
sys.path.insert(0, str(ROOT))

from options_analytics.surface_transforms import (  # noqa: E402
    MONEYNESS_RANGES,
    SURFACE_VIEWS,
    moneyness_range_label,
)

OUT = ROOT / "docs" / "images"

RECT = """(() => {
  const r = (%s).getBoundingClientRect();
  return [r.x, r.y, r.width, r.height];
})()"""
HEADING = "[...document.querySelectorAll('h2,h3')].find(h => h.innerText.trim() === %r)"
VISIBLE_PLOT = (
    "[...document.querySelectorAll('.js-plotly-plot')]"
    ".filter(e => e.getBoundingClientRect().width > 0)[%d]"
)


class Page:
    def __init__(self, ws):
        self.ws = ws
        self.ids = itertools.count(1)

    async def call(self, method, **params):
        i = next(self.ids)
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == i:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]

    async def js(self, expression):
        result = await self.call(
            "Runtime.evaluate", expression=expression,
            awaitPromise=True, returnByValue=True,
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    async def rect(self, element):
        return await self.js(RECT % element)

    async def save(self, name, x, y, width, height):
        shot = await self.call(
            "Page.captureScreenshot", format="png",
            clip={"x": x, "y": y, "width": width, "height": height, "scale": 1.5},
        )
        image = Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGB")
        image.save(OUT / f"{name}.jpg", quality=85, optimize=True)
        print("saved", OUT / f"{name}.jpg")

    async def click_choice(self, key, label):
        """Click one option of the segmented control with widget key ``key``."""
        await self.js(
            "[...document.querySelectorAll('.st-key-%s button')]"
            ".find(b => b.innerText.trim() === %r).click()" % (key, label)
        )
        await asyncio.sleep(4)

    async def click_tab(self, label):
        await self.js(
            "[...document.querySelectorAll('[role=tab],[data-baseweb=tab]')]"
            ".find(b => b.innerText.trim() === %r).click()" % label
        )
        await asyncio.sleep(4)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def open_page(browser, url, scheme):
    """A headless browser page on ``url`` in ``scheme``, loaded and settled."""
    port = free_port()
    process = subprocess.Popen(
        [browser, "--headless", f"--remote-debugging-port={port}",
         "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                break
            except OSError:
                time.sleep(0.2)
        target = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            page = Page(ws)
            # A tall viewport keeps Streamlit's inner scroll container from scrolling.
            await page.call(
                "Emulation.setDeviceMetricsOverride",
                width=1400, height=4000, deviceScaleFactor=1, mobile=False,
            )
            await page.call(
                "Emulation.setEmulatedMedia",
                features=[{"name": "prefers-color-scheme", "value": scheme}],
            )
            await page.call("Page.navigate", url=url)
            await asyncio.sleep(25)
            yield page
    finally:
        process.kill()


async def capture_states(browser, url, scheme="dark"):
    """Save the IV surface tab for every moneyness range in each surface view."""
    async with open_page(browser, url, scheme) as page:
        for name in MONEYNESS_RANGES:
            await page.click_choice("moneyness_range", moneyness_range_label(name))
            for view in SURFACE_VIEWS:
                await page.click_choice("surface_view", view)
                controls = await page.rect("document.querySelector('.st-key-surface_view')")
                plot = await page.rect(VISIBLE_PLOT % 1)
                await page.save(
                    f"surface-{name.lower().replace(' ', '-')}-{view.lower()}",
                    controls[0] - 8, controls[1] - 8,
                    plot[2] + 16, plot[1] + plot[3] - controls[1] + 16,
                )


async def capture(browser, url, scheme="dark"):
    async with open_page(browser, url, scheme) as page:
        top = await page.rect(HEADING % "Open interest and gamma exposure")
        positioning = await page.rect(VISIBLE_PLOT % 0)
        x = top[0] - 8
        await page.save(
            "oi-gex", x, top[1] - 8, positioning[2] + 16,
            positioning[1] + positioning[3] - top[1] + 16,
        )

        iv = await page.rect(HEADING % "Implied volatility")
        heatmap = await page.rect(VISIBLE_PLOT % 1)
        await page.save(
            "heatmap", x, iv[1] - 8, heatmap[2] + 16, heatmap[1] + heatmap[3] - iv[1] + 16,
        )

        await page.click_choice("surface_view", "3D")
        controls = await page.rect("document.querySelector('.st-key-surface_view')")
        surface = await page.rect(VISIBLE_PLOT % 1)
        await page.save(
            "surface", x, controls[1] - 8, surface[2] + 16,
            surface[1] + surface[3] - controls[1] + 16,
        )

        for label, name in [("IV smiles", "iv-smiles"),
                            ("ATM term structure", "atm-term-structure")]:
            await page.click_tab(label)
            plot = await page.rect(VISIBLE_PLOT % 1)
            await page.save(name, plot[0] - 8, plot[1] - 8, plot[2] + 16, plot[3] + 16)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--browser", required=True, help="Chromium binary")
    parser.add_argument("--url", default="http://localhost:8599")
    parser.add_argument("--scheme", choices=["dark", "light"], default="dark")
    parser.add_argument("--out", type=Path, default=OUT, help="image directory")
    parser.add_argument(
        "--states", action="store_true",
        help="save the IV surface for every moneyness range and view instead",
    )
    args = parser.parse_args()
    out = args.out.resolve()
    if (args.states or args.scheme != "dark") and (out == OUT or OUT in out.parents):
        parser.error(
            "--states and --scheme light need --out with a directory outside docs/images/"
        )
    OUT = args.out
    OUT.mkdir(parents=True, exist_ok=True)
    run = capture_states if args.states else capture
    asyncio.run(run(args.browser, args.url, args.scheme))


if __name__ == "__main__":
    main()
