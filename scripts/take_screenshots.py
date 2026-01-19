"""Take screenshots of all page types in the application."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def take_screenshots() -> None:
    """Take screenshots of all page types."""
    base_url = "http://localhost:8000"
    screenshots_dir = Path(__file__).parent.parent / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        screenshots = [
            ("home", "/"),
            ("agencies_list", "/agencies"),
            ("titles_list", "/titles"),
            ("search_form", "/search"),
        ]

        # Take basic page screenshots
        for name, path in screenshots:
            print(f"Taking screenshot: {name} ({path})")
            await page.goto(f"{base_url}{path}")
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path=screenshots_dir / f"{name}.png", full_page=True)

        # Take screenshot of agency detail (try to get first agency from API)
        print("Finding an agency for detail page...")
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/api/v1/agencies/", params={"limit": 1})
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        agency_id = data[0]["id"]
                        await page.goto(f"{base_url}/agencies/{agency_id}/details")
                        await page.wait_for_load_state("networkidle")
                        await page.screenshot(path=screenshots_dir / "agency_detail.png", full_page=True)
                        print("Screenshot taken: agency_detail")
                    else:
                        print("No agencies found in database")
                else:
                    print(f"API returned status {response.status_code}")
        except Exception as e:
            print(f"Error fetching agency: {e}")

        # Take screenshot of CFR detail (need to find a CFR ID first)
        print("Finding a CFR reference for detail page...")
        await page.goto(f"{base_url}/titles")
        await page.wait_for_load_state("networkidle")

        # Look for a CFR link
        cfr_link = page.locator('a[href*="/cfr/"]').first
        if await cfr_link.count() > 0:
            await cfr_link.click()
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path=screenshots_dir / "cfr_detail.png", full_page=True)
            print("Screenshot taken: cfr_detail")
        else:
            print("No CFR references found")

        # Take screenshot of local search results
        print("Taking screenshot: local_search_results")
        await page.goto(f"{base_url}/search/local?q=environmental")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=screenshots_dir / "local_search_results.png", full_page=True)

        # Take screenshot of external search results
        print("Taking screenshot: external_search_results")
        await page.goto(f"{base_url}/search/results?q=environmental")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=screenshots_dir / "external_search_results.png", full_page=True)

        await browser.close()

    print(f"\nAll screenshots saved to: {screenshots_dir}")
    print("\nScreenshots taken:")
    for screenshot in sorted(screenshots_dir.glob("*.png")):
        print(f"  - {screenshot.name}")


if __name__ == "__main__":
    asyncio.run(take_screenshots())
