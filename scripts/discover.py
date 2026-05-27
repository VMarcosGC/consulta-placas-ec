"""Script de descubrimiento: abre un portal con Playwright, toma screenshot y
vuelca estructura (frames, inputs, selects, buttons) para diseñar el scraper
sin trial-and-error.

Uso:
    python scripts/discover.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


async def descubrir(url: str, nombre: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(60000)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[{nombre}] goto falló: {e!r}")

        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass

        await page.wait_for_timeout(3000)

        await page.screenshot(path=f"discover_{nombre}.png", full_page=True)

        lineas = [f"URL: {url}", f"Total frames: {len(page.frames)}", ""]
        for i, fr in enumerate(page.frames):
            try:
                n_inputs = await fr.locator("input").count()
                n_selects = await fr.locator("select").count()
                n_buttons = await fr.locator("button").count()
                lineas.append(
                    f"Frame {i}: url={fr.url}\n"
                    f"  inputs={n_inputs}, selects={n_selects}, buttons={n_buttons}"
                )
                # Detalle de cada select (opciones)
                for j in range(min(n_selects, 5)):
                    s = fr.locator("select").nth(j)
                    try:
                        opciones = await s.locator("option").all_text_contents()
                        lineas.append(f"    select[{j}] opciones: {opciones}")
                    except Exception:
                        pass
                # Detalle de inputs (placeholders, name)
                for j in range(min(n_inputs, 8)):
                    inp = fr.locator("input").nth(j)
                    try:
                        attrs = await inp.evaluate(
                            "el => ({type: el.type, name: el.name, id: el.id,"
                            " placeholder: el.placeholder, visible: el.offsetParent !== null})"
                        )
                        lineas.append(f"    input[{j}]: {attrs}")
                    except Exception:
                        pass
                # Detalle de botones
                for j in range(min(n_buttons, 5)):
                    b = fr.locator("button").nth(j)
                    try:
                        txt = (await b.text_content() or "").strip()
                        lineas.append(f"    button[{j}]: {txt!r}")
                    except Exception:
                        pass
            except Exception as e:
                lineas.append(f"Frame {i}: error inspeccionando: {e!r}")

        with open(f"discover_{nombre}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))

        print(f"[{nombre}] OK — discover_{nombre}.png + discover_{nombre}.txt")
        await browser.close()


async def main():
    # Editar los portales a descubrir según lo que se necesite.
    await descubrir(
        "https://www.gestiondefiscalias.gob.ec/siaf/informacion/web/noticiasdelito/index.php",
        "fiscalia",
    )


if __name__ == "__main__":
    asyncio.run(main())
