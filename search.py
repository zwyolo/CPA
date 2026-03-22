"""
CPA Exam Availability Checker — single run, no config file.

Usage:
  python search.py --exam "Auditing and Attestation" \
                   --city "Alpharetta" --state GA \
                   --start 2026-04-01 --end 2026-04-30 \
                   [--headless]
"""

import argparse
import json
import re
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

import captcha as captcha_mod

URL = "https://proscheduler.prometric.com/scheduling/searchAvailability"
TIME_PATTERN = re.compile(r"\d{1,2}:\d{2}\s*[AP]M", re.IGNORECASE)


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def _fmt_date(date_str: str) -> str:
    """'2026-04-01' → '04/01/2026'"""
    y, m, d = date_str.split("-")
    return f"{m}/{d}/{y}"


def js_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", element)


def make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()

    # 👇 指定 Docker 里的 Chromium
    opts.binary_location = "/usr/bin/chromium"

    if headless:
        opts.add_argument("--headless=new")

    opts.add_argument("--window-size=1280,900")

    # 👇 Docker 必备（非常重要）
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    # 可选优化
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    # 👇 用系统自带 chromedriver
    service = Service("/usr/bin/chromedriver")

    return webdriver.Chrome(service=service, options=opts)


def _get_time_slots(driver: webdriver.Chrome) -> list[str]:
    time.sleep(1)
    candidates = [
        "div.time-card",
        "div.time-slot",
        "button.time-slot",
        "li.time-slot",
        "div[class*='timecard']",
        "div[class*='time-card']",
        "div[class*='timeslot']",
        "div[class*='appointment-time']",
        "ul.timeslots li",
        "div.col-sm-3.col-xs-6",
    ]
    for sel in candidates:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        times = [e.text.strip() for e in els if TIME_PATTERN.search(e.text)]
        if times:
            return times
    body_text = driver.find_element(
        By.CSS_SELECTOR, "div.card.card-default.marginBottom"
    ).text
    return TIME_PATTERN.findall(body_text)


def _scrape_results(driver: webdriver.Chrome, wait: WebDriverWait) -> list:
    results = []
    for card in driver.find_elements(
        By.CSS_SELECTOR, "div.card.card-default.marginBottom"
    ):
        try:
            h2_els = card.find_elements(By.CSS_SELECTOR, "h2.location-heading")
            if not h2_els:
                continue
            header = h2_els[0].text.strip()

            distance = ""
            dist_els = card.find_elements(By.CSS_SELECTOR, "span#mi")
            if dist_els:
                distance = dist_els[0].text.strip()
            if distance:
                try:
                    if float(distance.split()[0]) > 100:
                        log(f"Skipping {header} ({distance} > 100 miles)")
                        continue
                except (ValueError, IndexError):
                    pass

            dates_with_times = []
            for dc in card.find_elements(By.CSS_SELECTOR, "div.date-card"):
                label = dc.get_attribute("aria-label") or ""
                date_str = (
                    label.split(", ", 1)[1].strip() if ", " in label else label.strip()
                )
                if not date_str:
                    continue
                try:
                    js_click(driver, dc)
                    times = _get_time_slots(driver)
                    try:
                        js_click(driver, dc)
                        time.sleep(0.3)
                    except Exception:
                        pass
                except Exception:
                    times = []
                dates_with_times.append({"date": date_str, "times": times})

            results.append(
                {
                    "center": header,
                    "distance": distance,
                    "available_dates": dates_with_times,
                }
            )
        except Exception:
            continue
    return results


def search_once(
    exam_section: str,
    city_or_zip: str,
    state: str,
    start_date: str,
    end_date: str,
    headless: bool = True,
):
    driver = make_driver(headless)
    wait = WebDriverWait(driver, 20)
    try:
        driver.get(URL)

        Select(
            wait.until(EC.element_to_be_clickable((By.ID, "test_sponsor")))
        ).select_by_visible_text("Uniform CPA Exam")
        Select(
            wait.until(EC.element_to_be_clickable((By.ID, "testProgram")))
        ).select_by_visible_text("Uniform CPA Exam")
        Select(
            wait.until(EC.element_to_be_clickable((By.ID, "testSelector")))
        ).select_by_visible_text(exam_section)
        log(f"Selected: {exam_section}")

        js_click(driver, wait.until(EC.presence_of_element_located((By.ID, "nextBtn"))))

        search_box = wait.until(
            EC.presence_of_element_located((By.ID, "searchLocation"))
        )
        search_box.clear()
        search_box.send_keys(f"{city_or_zip}, {state}")
        time.sleep(1)
        search_box.send_keys(Keys.ARROW_DOWN)
        search_box.send_keys(Keys.ENTER)
        time.sleep(0.5)

        start_inp = wait.until(EC.element_to_be_clickable((By.ID, "locationStartDate")))
        start_inp.click()
        start_inp.send_keys(Keys.COMMAND + "a")
        start_inp.send_keys(_fmt_date(start_date))
        start_inp.send_keys(Keys.TAB)
        time.sleep(1)

        end_inp = driver.find_element(By.ID, "locationEndDate")
        end_inp.click()
        end_inp.send_keys(Keys.COMMAND + "a")
        end_inp.send_keys(_fmt_date(end_date))
        end_inp.send_keys(Keys.TAB)
        log(f"Dates: {_fmt_date(start_date)} → {_fmt_date(end_date)}")

        def get_captcha_image():
            img = wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "img[src*='captcha'], .captcha img, img[alt*='captcha' i]",
                    )
                )
            )
            return driver.execute_script(
                """
                const img = arguments[0];
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
                canvas.getContext('2d').drawImage(img, 0, 0);
                return canvas.toDataURL('image/png').split(',')[1];
            """,
                img,
            )

        def try_answer(answer):
            inp = driver.find_element(
                By.CSS_SELECTOR,
                "input[placeholder*='captcha' i], input[id*='captcha' i], input[name*='captcha' i]",
            )
            inp.clear()
            inp.send_keys(answer)
            js_click(
                driver, wait.until(EC.presence_of_element_located((By.ID, "nextBtn")))
            )
            time.sleep(3)
            return not driver.find_elements(
                By.XPATH,
                "//*[contains(text(),'The text you have entered is not correct')]",
            )

        def refresh_captcha():
            for btn in driver.find_elements(By.XPATH, "//*[@title='Reset captcha']"):
                btn.click()
                break
            time.sleep(1)

        solved = False
        for attempt in range(5):
            answer = captcha_mod.solve(get_captcha_image())
            log(f"CAPTCHA attempt {attempt + 1}: '{answer}'")
            if try_answer(answer):
                log("CAPTCHA accepted.")
                solved = True
                break
            log("CAPTCHA wrong, refreshing...")
            refresh_captcha()

        if not solved:
            log("CAPTCHA failed after 5 attempts.")
            return

        log("Search submitted.")
        try:
            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.card.card-default.marginBottom")
                )
            )
        except Exception:
            time.sleep(4)

        results = _scrape_results(driver, wait)
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
        driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exam", required=True, help="Exam section name")
    parser.add_argument("--city", required=True, help="City or ZIP")
    parser.add_argument("--state", required=True, help="State abbreviation (e.g. GA)")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    args = parser.parse_args()

    search_once(
        exam_section=args.exam,
        city_or_zip=args.city,
        state=args.state,
        start_date=args.start,
        end_date=args.end,
        headless=args.headless,
    )
