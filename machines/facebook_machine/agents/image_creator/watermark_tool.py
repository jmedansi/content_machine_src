import os
import sys
import subprocess
import cv2
import numpy as np


def erase_gemini_watermark(image_path, output_path=None):
    """
    Supprime le filigrane Gemini (Imagen 3) via OpenCV inpainting.
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
        # Le logo Gemini fait ~50-70px, avec une marge de ~10px du bord
        margin = 8
        zone_size = max(70, int(min(h, w) * 0.08))
        y1 = max(0, h - zone_size - margin)
        y2 = h - margin
        x1 = max(0, w - zone_size - margin)
        x2 = w - margin

        roi = img[y1:y2, x1:x2].copy()

        # Détection du filigrane par contraste de luminance
        # Le logo est plus brillant que le fond environnant
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray_roi, (21, 21), 0)
        diff = cv2.absdiff(gray_roi, blurred)

        # Seuil adaptatif : le filigrane a un contraste élevé vs le fond lissé
        _, mask_roi = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)

        # Dilater le masque pour couvrir les bords du logo
        kernel = np.ones((3, 3), np.uint8)
        mask_roi = cv2.dilate(mask_roi, kernel, iterations=2)

        # Vérifier qu'on a bien détecté quelque chose
        if np.sum(mask_roi > 0) < 50:
            # Pas de filigrane détecté — image probablement déjà propre
            print(f"[INFO] Aucun filigrane détecté dans la zone ROI ({os.path.basename(image_path)})")
            if target != image_path:
                cv2.imwrite(target, img)
            return True

        # Construire le masque plein
        mask_full = np.zeros((h, w), dtype=np.uint8)
        mask_full[y1:y2, x1:x2] = mask_roi

        # InpaintingTelea — algorithme de Navier-Stokes
        radius = 3
        cleaned = cv2.inpaint(img, mask_full, radius, cv2.INPAINT_TELEA)

        # Sauvegarder
        cv2.imwrite(target, cleaned)
        pixels_cleaned = int(np.sum(mask_roi > 0))
        print(f"[SUCCESS] Filigrane supprimé via OpenCV inpainting ({pixels_cleaned}px) : {os.path.basename(target)}")
        return True

    except Exception as e:
        print(f"[ERROR] Échec OpenCV inpainting : {e}")
        # Fallback : essayer l'ancienne méthode
        return _fallback_old_library(image_path, target)


def _fallback_old_library(image_path, output_path):
    """Fallback : utilise py-gemini-watermark-remover (alpha inverse)."""
    try:
        from gemini_watermark_remover import process_image
        success = process_image(image_path, output_path, auto_detect=True)
        if success:
            print(f"[SUCCESS] Filigrane supprimé via Python API : {os.path.basename(output_path)}")
            return True
        else:
            print("[WARN] process_image a retourné False (alpha maps peut-être obsolètes).")
            return False
    except ImportError:
        print("[WARN] py-gemini-watermark-remover non installé.")
        return False
    except Exception as e:
        print(f"[WARN] Échec du fallback Python API : {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        erase_gemini_watermark(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
