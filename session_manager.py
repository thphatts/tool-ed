import asyncio
from playwright.async_api import async_playwright
import os
from settings import (
    CHROMIUM_ARGS as CONFIG_CHROMIUM_ARGS,
    ORIGIN,
    PASSWORD,
    STORAGE_STATE,
    URL,
    USERNAME,
    require_login_config,
)

FAKE_MIC_AUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_artifacts", "interact.wav")

CHROMIUM_ARGS = [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    f"--use-file-for-fake-audio-capture={FAKE_MIC_AUDIO}",
    *CONFIG_CHROMIUM_ARGS,
]

async def check_and_handle_duplicate_modal(page):
    """Kiểm tra và click ngay nút 'Login on This Device' nếu có modal đăng nhập trùng"""
    try:
        modal_btn = page.locator("input[value='Login on This Device'], #confirmModal #btnOk, button:has-text('Login on This Device'), .okButton.utils__BSOKBtn").first
        if await modal_btn.count() > 0 and await modal_btn.is_visible():
            print("[*] Phát hiện hộp thoại 'You are already logged in to English Discoveries'!")
            print("[*] Đang tự động bấm 'Login on This Device' để giành quyền đăng nhập...")
            await modal_btn.click(force=True)
            await page.wait_for_timeout(3000)
            return True
    except Exception:
        pass
    return False

async def perform_full_login(page, context):
    """Thực hiện quy trình đăng nhập đầy đủ từ đầu"""
    require_login_config()
    print("[*] Đang điều hướng đến trang đăng nhập...")
    await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(2000)

    user_input = await page.wait_for_selector("input[name='userName']", timeout=20000)
    pass_input = await page.wait_for_selector("input[name='password']", timeout=20000)
    submit_btn = await page.wait_for_selector("input#submit1", timeout=20000)

    print("[*] Đang điền thông tin đăng nhập từ biến môi trường...")
    await user_input.click()
    await user_input.fill("")
    await user_input.type(USERNAME, delay=30)

    await pass_input.click()
    await pass_input.fill("")
    await pass_input.type(PASSWORD, delay=30)
    await page.wait_for_timeout(500)
    await submit_btn.click()

    print("[*] Đang theo dõi chuyển hướng và xử lý modal trùng phiên...")
    for sec in range(25):
        await page.wait_for_timeout(1000)
        await check_and_handle_duplicate_modal(page)
        
        # Nếu đã vào tới Dashboard
        if "#/home" in page.url and not await page.locator("input[name='userName']").is_visible():
            has_dashboard = await page.locator(".carouselStartBtnW, .home__allUnitsW").count()
            if has_dashboard > 0:
                print("[*] Đăng nhập thành công vào Dashboard!")
                break

    await page.wait_for_timeout(3000)
    await context.storage_state(path=STORAGE_STATE)
    print(f"[*] Đã lưu trạng thái phiên mới vào: {STORAGE_STATE}")

async def ensure_logged_in(p, headless=True):
    """Đảm bảo luôn đăng nhập thành công kể cả khi phiên cũ bị ghi đè từ thiết bị khác"""
    require_login_config()
    # 1. Thử dùng session cũ nếu có
    if os.path.exists(STORAGE_STATE):
        print("[*] Đã tìm thấy session lưu trước đó, đang kiểm tra...")
        browser = await p.chromium.launch(headless=headless, args=CHROMIUM_ARGS)
        context = await browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1280, "height": 800})
        if ORIGIN:
            await context.grant_permissions(["microphone"], origin=ORIGIN)
        page = await context.new_page()

        try:
            await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)

            # Xử lý nếu hiện modal trùng phiên ngay khi nạp cookie
            await check_and_handle_duplicate_modal(page)

            # Kiểm tra xem có đang ở Dashboard thật sự hay bị văng ra form đăng nhập
            is_login_form = await page.locator("input[name='userName']").count() > 0 and await page.locator("input[name='userName']").is_visible()
            if "#/home" in page.url and not is_login_form:
                print("[*] Phiên đăng nhập hợp lệ! Đã vào thẳng Dashboard.")
                return browser, context, page
        except Exception as e:
            print(f"[!] Lỗi khi nạp session cũ: {e}")

        print("[!] Phiên đăng nhập cũ đã hết hạn hoặc bị ghi đè từ trình duyệt khác. Đang tự động đăng nhập lại...")
        await browser.close()

    # 2. Đăng nhập mới hoàn toàn
    browser = await p.chromium.launch(headless=headless, args=CHROMIUM_ARGS)
    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    if ORIGIN:
        await context.grant_permissions(["microphone"], origin=ORIGIN)
    page = await context.new_page()

    await perform_full_login(page, context)
    return browser, context, page

async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        print(f"[*] Sẵn sàng! URL hiện tại: {page.url}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
