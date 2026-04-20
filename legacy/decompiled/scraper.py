import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

# Set HEADLESS = False to see the browser while debugging
HEADLESS = True


def _interruptible_sleep(seconds: float, stop_event=None, interval: float = 0.25) -> bool:
    """Sleep in short intervals so a stop request can abort quickly."""
    end_time = time.time() + seconds
    while time.time() < end_time:
        if stop_event is not None and stop_event.is_set():
            return False
        remaining = end_time - time.time()
        time.sleep(min(interval, max(0, remaining)))
    return True


def _stop_requested(stop_event) -> bool:
    return stop_event is not None and stop_event.is_set()


def get_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=options)

    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


def _apply_sort_latest(driver, stop_event=None):
    """
    Open the Sort By dropdown and select 'Bid End Date: Latest First'.

    GeM uses a Bootstrap dropdown — steps:
      1. Click the dropdown toggle button to open the menu
      2. Click 'Bid End Date: Latest First' inside the menu
      3. Wait for page to re-render

    Four fallback strategies tried in order.
    """
    wait = WebDriverWait(driver, 10)

    # ── Strategy 1: click dropdown toggle, then find option ─────────────────
    try:
        toggle = driver.find_element(By.XPATH,
            "//button[contains(@class,'dropdown-toggle') and ("
            "contains(translate(text(),'SORTBY ','sortby '),'sort') or "
            "contains(@id,'sort') or contains(@data-toggle,'dropdown'))]"
        )
        driver.execute_script("arguments[0].click();", toggle)
        if not _interruptible_sleep(1, stop_event):
            return False

        option = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//*[contains(text(),'Bid End Date: Latest First') or "
            "contains(text(),'Bid End Date : Latest First')]"
        )))
        driver.execute_script("arguments[0].click();", option)
        if not _interruptible_sleep(5, stop_event):
            return False
        print("   ✓ Sorted: Bid End Date Latest First (S1)")
        return True
    except Exception:
        pass

    # ── Strategy 2: option already visible in DOM ────────────────────────────
    try:
        option = driver.find_element(By.XPATH,
            "//*[contains(text(),'Bid End Date: Latest First') or "
            "contains(text(),'Bid End Date : Latest First')]"
        )
        driver.execute_script("arguments[0].click();", option)
        if not _interruptible_sleep(5, stop_event):
            return False
        print("   ✓ Sorted: Bid End Date Latest First (S2)")
        return True
    except Exception:
        pass

    # ── Strategy 3: try known element IDs GeM has used ──────────────────────
    for id_val in ["Bid-End-Date-Latest", "bidEndDateLatest",
                   "bid-end-date-latest", "endDateLatest"]:
        try:
            el = driver.find_element(By.ID, id_val)
            driver.execute_script("arguments[0].click();", el)
            if not _interruptible_sleep(5, stop_event):
                return False
            print(f"   ✓ Sorted by ID '{id_val}' (S3)")
            return True
        except Exception:
            continue

    # ── Strategy 4: case-insensitive anchor text match ───────────────────────
    try:
        option = driver.find_element(By.XPATH,
            "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            "'abcdefghijklmnopqrstuvwxyz'),'bid start date') and "
            "contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            "'abcdefghijklmnopqrstuvwxyz'),'latest')]"
        )
        driver.execute_script("arguments[0].click();", option)
        if not _interruptible_sleep(5, stop_event):
            return False
        print("   ✓ Sorted via anchor text (S4)")
        return True
    except Exception:
        pass

    print("   ⚠ Sort failed — all 4 strategies exhausted, continuing unsorted")
    return False


def search_keyword(driver, keyword: str, stop_event=None):
    """Type keyword, press Enter, apply sort, wait for results."""
    wait = WebDriverWait(driver, 20)

    inputs = driver.find_elements(By.ID, "searchBid")
    search_box = next((i for i in inputs if i.is_displayed()), None)

    if not search_box:
        search_box = wait.until(
            EC.presence_of_element_located((By.ID, "searchBid"))
        )

    if stop_event is not None and stop_event.is_set():
        return False

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", search_box)
    if not _interruptible_sleep(0.5, stop_event):
        return False
    search_box.clear()
    search_box.send_keys(keyword)
    search_box.send_keys(Keys.ENTER)

    # Wait for initial results
    if not _interruptible_sleep(7, stop_event):
        return False
    wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "block_header")))

    # Apply sort. Sort failure should not stop scraping; only a real stop request should.
    sorted_ok = _apply_sort_latest(driver, stop_event=stop_event)
    if not sorted_ok and _stop_requested(stop_event):
        return False

    # Wait for re-render after sort
    if not _interruptible_sleep(4, stop_event):
        return False
    wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "block_header")))
    return True


def _card_snapshot(card):
    """Capture stable card data before scrolling/pagination can stale the element."""
    parent = card.find_element(By.XPATH, "..")
    text = parent.text
    href = ""

    try:
        anchor = card.find_element(By.CSS_SELECTOR, "a.bid_no_hover")
        href = anchor.get_attribute("href") or ""
    except Exception:
        try:
            anchor = parent.find_element(By.CSS_SELECTOR, "a.bid_no_hover")
            href = anchor.get_attribute("href") or ""
        except Exception:
            href = ""

    if href and not href.startswith("http"):
        href = "https://bidplus.gem.gov.in" + href

    return {"text": text, "pdf_url": href or "N/A"}


def _snapshot_key(snapshot: dict) -> str:
    href = snapshot.get("pdf_url", "")
    text = snapshot.get("text", "")
    return href if href and href != "N/A" else text[:300]


def _collect_visible_cards(driver, collected: list, seen: set, limit: int) -> None:
    for card in driver.find_elements(By.CLASS_NAME, "block_header"):
        if len(collected) >= limit:
            return
        try:
            snapshot = _card_snapshot(card)
        except Exception:
            continue

        key = _snapshot_key(snapshot)
        if key and key not in seen:
            seen.add(key)
            collected.append(snapshot)


def _scroll_for_more_cards(driver, collected: list, seen: set, limit: int, stop_event=None) -> bool:
    """Try lazy-loading more cards on the current result page."""
    start_count = len(collected)
    previous_count = start_count
    last_height = driver.execute_script("return document.body.scrollHeight")

    for _ in range(4):
        if len(collected) >= limit or _stop_requested(stop_event):
            break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        if not _interruptible_sleep(1.5, stop_event):
            break
        _collect_visible_cards(driver, collected, seen, limit)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height and len(collected) == previous_count:
            break
        last_height = new_height
        previous_count = len(collected)

    driver.execute_script("window.scrollTo(0, 0);")
    return len(collected) > start_count


def _click_next_page(driver, stop_event=None) -> bool:
    """
    Move to the next GeM result page if pagination exists.
    Covers anchors/buttons and common disabled pagination markers.
    """
    if _stop_requested(stop_event):
        return False

    next_xpaths = [
        "//a[normalize-space()='Next' and not(contains(@class,'disabled'))]",
        "//a[contains(translate(@aria-label,'NEXT','next'),'next') and not(contains(@class,'disabled'))]",
        "//button[normalize-space()='Next' and not(@disabled)]",
        "//*[contains(@class,'pagination')]//a[contains(.,'>') and not(contains(@class,'disabled'))]",
        "//*[contains(@class,'pagination')]//li[not(contains(@class,'disabled'))]/a[contains(translate(.,'NEXT','next'),'next')]",
    ]

    before = ""
    cards = driver.find_elements(By.CLASS_NAME, "block_header")
    if cards:
        try:
            before = cards[0].text
        except Exception:
            before = ""

    for xpath in next_xpaths:
        try:
            candidates = [el for el in driver.find_elements(By.XPATH, xpath) if el.is_displayed()]
            if not candidates:
                continue

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", candidates[0])
            if not _interruptible_sleep(0.3, stop_event):
                return False
            driver.execute_script("arguments[0].click();", candidates[0])
            if not _interruptible_sleep(3, stop_event):
                return False

            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "block_header"))
            )

            after_cards = driver.find_elements(By.CLASS_NAME, "block_header")
            after = after_cards[0].text if after_cards else ""
            if not before or after != before:
                print("   -> Moved to next results page")
                return True
        except Exception:
            continue

    return False


def get_bid_cards(driver, limit: int = 15, stop_event=None):
    """
    Return up to `limit` bid-card snapshots.

    GeM commonly renders 10 cards per page. This collects visible cards, tries
    lazy-load scrolling, then follows pagination while snapshotting data before
    old Selenium elements become stale.
    """
    collected = []
    seen = set()

    while len(collected) < limit and not _stop_requested(stop_event):
        _collect_visible_cards(driver, collected, seen, limit)
        if len(collected) >= limit:
            break

        grew = _scroll_for_more_cards(driver, collected, seen, limit, stop_event=stop_event)
        if len(collected) >= limit:
            break

        if not grew and not _click_next_page(driver, stop_event=stop_event):
            break

    return collected[:limit]
