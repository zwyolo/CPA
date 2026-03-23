"""
CPA Exam Availability Checker — Refactored to Playwright with Stealth & Optimizations.
"""

import argparse
import json
import re
import platform
import base64
from datetime import datetime
from playwright.sync_api import sync_playwright, expect
from playwright_stealth import Stealth

import captcha as captcha_mod

URL = "https://proscheduler.prometric.com/scheduling/searchAvailability"

def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def _fmt_date(date_str: str) -> str:
    """'2026-04-01' -> '04/01/2026'"""
    parts = date_str.split("-")
    if len(parts) == 3:
        return f"{parts[1]}/{parts[2]}/{parts[0]}"
    return date_str

def _get_time_slots(page) -> list[str]:
    """
    Tries to capture time slots after clicking a date.
    Prioritizes absolute accuracy by being "slow and steady".
    """
    # 1. Increased mandatory wait to ensure the site clears the previous results
    page.wait_for_timeout(1500) 
    
    candidates = [
        "div.time-card", "div.time-slot", "button.time-slot", "li.time-slot",
        "div[class*='timecard']", "div[class*='time-card']", "div[class*='timeslot']",
        "div[class*='appointment-time']", "ul.timeslots li", "div.col-sm-3.col-xs-6",
    ]
    time_pattern = re.compile(r'\d{1,2}:\d{2}\s*[AP]M', re.IGNORECASE)

    # 2. Longer retry loop with more spacing
    for _ in range(10):
        # Look for specific time elements
        for sel in candidates:
            els = page.query_selector_all(sel)
            texts = [e.inner_text().strip() for e in els if e.inner_text().strip()]
            times = [t for t in texts if time_pattern.search(t)]
            if times:
                # Extra grace period to ensure all slots are populated
                page.wait_for_timeout(500)
                return times

        # Check for "Loading" text or spinner to avoid premature scraping
        body_text = page.inner_text("body")
        if "Loading" in body_text or "Please wait" in body_text:
            page.wait_for_timeout(1000)
            continue

        # Fallback to container text
        try:
            container = page.locator("div.card.card-default.marginBottom").first
            if container.is_visible():
                times = time_pattern.findall(container.inner_text())
                if times:
                    page.wait_for_timeout(500)
                    return times
        except:
            pass

        page.wait_for_timeout(500)

    return []

def _scrape_results(page) -> list:
    results = []
    page.wait_for_selector("div.card.card-default.marginBottom", timeout=15000)
    cards = page.query_selector_all("div.card.card-default.marginBottom")

    for card in cards:
        try:
            h2_el = card.query_selector("h2.location-heading")
            if not h2_el: continue
            header = h2_el.inner_text().strip()

            distance = ""
            dist_el = card.query_selector("span#mi")
            if dist_el:
                distance = dist_el.inner_text().strip()
            
            # Simple 100 mile filter
            if distance:
                try:
                    miles = float(distance.split()[0])
                    if miles > 100:
                        log(f"Skipping {header} ({distance} > 100 miles)")
                        continue
                except: pass

            dates_with_times = []
            date_cards = card.query_selector_all("div.date-card")
            for dc in date_cards:
                label = dc.get_attribute("aria-label") or ""
                if ", " in label:
                    label = label.split(", ", 1)[1]
                date_str = label.strip()
                if not date_str: continue

                try:
                    dc.scroll_into_view_if_needed()
                    # Wait for scrolling to settle
                    page.wait_for_timeout(400)
                    # Natural click (no force) allows Playwright to wait for actionability
                    dc.click()
                    times = _get_time_slots(page)
                except Exception as e:
                    log(f"  Error clicking date {date_str}: {e}")
                    times = []

                dates_with_times.append({"date": date_str, "times": times})

            results.append({
                "center": header,
                "distance": distance,
                "available_dates": dates_with_times,
            })
        except Exception as e:
            log(f"Error scraping card: {e}")
            continue
    return results

def search_once(exam_section, city_or_zip, state, start_date, end_date, headless=True, captcha_solver="ddddocr", captcha_key=""):
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless, channel="chrome")
        except:
            browser = p.chromium.launch(headless=headless)

        context = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        try:
            page.goto(URL, wait_until="networkidle")
            
            # Step 1: Select exam
            page.select_option("#test_sponsor", label="Uniform CPA Exam")
            page.select_option("#testProgram", label="Uniform CPA Exam")
            page.select_option("#testSelector", label=exam_section)
            log(f"Selected: {exam_section}")

            page.click("#nextBtn")

            # Step 2: Address & dates
            search_box = page.locator("#searchLocation")
            search_box.fill(f"{city_or_zip}, {state}")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")

            modifier = "Meta" if platform.system() == "Darwin" else "Control"

            # Fill dates
            for selector, d_str in [("#locationStartDate", start_date), ("#locationEndDate", end_date)]:
                inp = page.locator(selector)
                inp.click()
                page.keyboard.press(f"{modifier}+a")
                page.keyboard.press("Backspace")
                page.keyboard.type(_fmt_date(d_str))
                page.keyboard.press("Tab")

            log(f"Dates: {_fmt_date(start_date)} -> {_fmt_date(end_date)}")

            # Step 3: CAPTCHA
            def get_captcha_image_b64():
                img = page.wait_for_selector("img[src*='captcha'], .captcha img, img[alt*='captcha' i]")
                return base64.b64encode(img.screenshot()).decode('utf-8')

            def try_answer(answer):
                captcha_input = page.locator("input#captcha, input[placeholder*='captcha' i]").first
                captcha_input.fill(answer)
                page.click("#nextBtn")
                
                try:
                    page.wait_for_function("""
                        () => document.querySelector('.card-default') || 
                              document.body.innerText.includes('not correct') ||
                              document.body.innerText.includes('No Availability Found')
                    """, timeout=10000)
                except:
                    pass

                error_exists = page.locator("//*[contains(text(),'not correct')]").is_visible()
                return not error_exists

            def refresh_captcha():
                refresh_btn = page.locator("//*[@title='Reset captcha']").first
                if refresh_btn.is_visible():
                    refresh_btn.click()
                    page.wait_for_timeout(500)

            solved = False
            for attempt in range(5):
                img_b64 = get_captcha_image_b64()
                answer = captcha_mod.solve(img_b64, method=captcha_solver, api_key=captcha_key)
                log(f"CAPTCHA attempt {attempt + 1}: '{answer}'")
                if not answer:
                    refresh_captcha(); continue
                if try_answer(answer):
                    log("CAPTCHA accepted.")
                    solved = True; break
                log("CAPTCHA wrong, refreshing...")
                refresh_captcha()

            if not solved:
                log("CAPTCHA failed.")
                return

            log("Search submitted. Waiting for results...")
            
            try:
                page.wait_for_function("""
                    () => document.querySelector('div.card.card-default.marginBottom') || 
                          document.body.innerText.includes('No Availability Found')
                """, timeout=30000)
            except:
                pass

            if "No Availability Found" in page.inner_text("body"):
                log("No availability found for these dates.")
                results = []
            else:
                results = _scrape_results(page)
            
            output = {
                "search_params": {
                    "exam_section": exam_section,
                    "location": f"{city_or_zip}, {state}",
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "scraped_at": datetime.now().isoformat(),
                "centers": results,
            }
            with open("availability_results.json", "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            log(f"Saved {len(results)} result(s) to availability_results.json")

        except Exception as e:
            log(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exam", required=True)
    parser.add_argument("--city", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--captcha-solver", default="ddddocr")
    parser.add_argument("--captcha-key", default="")
    args = parser.parse_args()

    search_once(args.exam, args.city, args.state, args.start, args.end, args.headless, args.captcha_solver, args.captcha_key)
