import os
from playwright.sync_api import sync_playwright

profile_path = r"C:\Users\jmeda\AppData\Local\Google\Chrome\User Data\Profile Tiers"

def main():
    print(f"Lancement de Chrome sur le profil : {profile_path}")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.facebook.com")
        print("Navigateur ouvert ! Connectez-vous, puis fermez le navigateur manuellement pour terminer le script.")
        
        # Garde le navigateur ouvert jusqu'à ce que tu le fermes manuellement
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        
        print("Navigateur fermé, session enregistrée !")

if __name__ == "__main__":
    main()
