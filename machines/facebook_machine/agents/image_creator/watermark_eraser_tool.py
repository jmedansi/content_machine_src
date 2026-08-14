import os
import sys
import cv2
import numpy as np


def erase_gemini_watermark(image_path, output_path=None):
    """
    Supprime le filigrane Gemini via OpenCV inpainting.
    Détecte la zone du logo dans le coin inférieur droit et utilise
    l'algorithme de Navier-Stokes (Telea) pour reconstruire les pixels.
    """
    if not os.path.exists(image_path):
        print(f"[ERROR] Fichier non trouvé : {image_path}")
        return False

    target = output_path if output_path else image_path

    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"[ERROR] Impossible de lire l'image : {image_path}")
            return False

        h, w = img.shape[:2]

        # Zone du filigrane : coin inférieur droit
        margin = 8
        zone_size = max(70, int(min(h, w) * 0.08))
        y1 = max(0, h - zone_size - margin)
        y2 = h - margin
        x1 = max(0, w - zone_size - margin)
        x2 = w - margin

        roi = img[y1:y2, x1:x2].copy()

        # Détection du filigrane par contraste de luminance
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray_roi, (21, 21), 0)
        diff = cv2.absdiff(gray_roi, blurred)

        _, mask_roi = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)

        kernel = np.ones((3, 3), np.uint8)
        mask_roi = cv2.dilate(mask_roi, kernel, iterations=2)

        if np.sum(mask_roi > 0) < 50:
            print(f"[INFO] Aucun filigrane détecté ({os.path.basename(image_path)})")
            if target != image_path:
                cv2.imwrite(target, img)
            return True

        mask_full = np.zeros((h, w), dtype=np.uint8)
        mask_full[y1:y2, x1:x2] = mask_roi

        cleaned = cv2.inpaint(img, mask_full, 3, cv2.INPAINT_TELEA)

        cv2.imwrite(target, cleaned)
        pixels_cleaned = int(np.sum(mask_roi > 0))
        print(f"[SUCCESS] Filigrane supprimé via OpenCV inpainting ({pixels_cleaned}px) : {os.path.basename(target)}")
        return True

    except Exception as e:
        print(f"[ERROR] Échec OpenCV inpainting : {e}")
        # Fallback : ancienne méthode
        try:
            from gemini_watermark_remover import process_image
            success = process_image(image_path, target, auto_detect=True)
            if success:
                print(f"[SUCCESS] Filigrane supprimé via Python API : {os.path.basename(target)}")
                return True
        except Exception:
            pass
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        erase_gemini_watermark(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print("Usage: python watermark_eraser_tool.py <image_path> [output_path]")
