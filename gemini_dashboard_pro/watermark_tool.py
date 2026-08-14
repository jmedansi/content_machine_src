import os
import sys
import subprocess

def erase_gemini_watermark(image_path, output_path=None):
    """
    Supprime le filigrane Gemini (Imagen 3) via la méthode de décomposition alpha inverse.
    La bibliothèque py-gemini-watermark-remover annule mathématiquement le composite
    alpha que Gemini applique, restituant les pixels d'origine sans flou ni artefact.
    """
    if not os.path.exists(image_path):
        print(f"[ERROR] Fichier non trouvé : {image_path}")
        return False

    target = output_path if output_path else image_path

    try:
        # On appelle le CLI de py-gemini-watermark-remover
        cmd = ["gemini-watermark", "-i", image_path, "-o", target]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"[SUCCESS] Filigrane supprimé (alpha-inverse) : {os.path.basename(target)}")
            return True
        else:
            print(f"[ERROR] gemini-watermark a échoué : {result.stderr.strip()}")
            # Fallback : essayer via import Python direct
            return _fallback_python_api(image_path, target)
    except FileNotFoundError:
        # Le CLI n'est pas dans le PATH, on essaie l'API Python directement
        print("[WARN] CLI gemini-watermark non trouvé, tentative via import Python...")
        return _fallback_python_api(image_path, target)
    except Exception as e:
        print(f"[ERROR] Erreur inattendue : {e}")
        return False


def _fallback_python_api(image_path, output_path):
    """Fallback : utilise directement l'API Python de py-gemini-watermark-remover."""
    try:
        from gemini_watermark_remover import process_image
        success = process_image(image_path, output_path, auto_detect=True)
        if success:
            print(f"[SUCCESS] Filigrane supprimé via Python API : {os.path.basename(output_path)}")
            return True
        else:
            print("[ERROR] process_image a retourné False.")
            return False
    except ImportError:
        print("[ERROR] py-gemini-watermark-remover n'est pas installé. Lancez : pip install py-gemini-watermark-remover")
        return False
    except Exception as e:
        print(f"[ERROR] Échec du fallback Python API : {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        erase_gemini_watermark(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
