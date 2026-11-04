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
`websockets` and `Pillow` packages, which the dashboard extra installs.
"""
import argparse
import asyncio
import base64
import io
import itertools
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websockets
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
PORT = 9333

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


async def capture(browser, url):
    process = subprocess.Popen(
        [browser, "--headless", f"--remote-debugging-port={PORT}",
         "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
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
                features=[{"name": "prefers-color-scheme", "value": "dark"}],
            )
            await page.call("Page.navigate", url=url)
            await asyncio.sleep(25)

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
    finally:
        process.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--browser", required=True, help="Chromium binary")
    parser.add_argument("--url", default="http://localhost:8599")
    args = parser.parse_args()
    asyncio.run(capture(args.browser, args.url))


if __name__ == "__main__":
    main()
