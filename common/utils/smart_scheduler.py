# smart_scheduler.py — Scheduler intelligent avec détection de conflits
# Usage: from common.utils.smart_scheduler import SmartScheduler

import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT_DIR))

logger = logging.getLogger(__name__)

try:
    from core.paths import PLATFORM_BASE
except ImportError:
    PLATFORM_BASE = {
        "facebook": _ROOT_DIR / "machines" / "facebook_machine",
        "linkedin": _ROOT_DIR / "machines" / "linkedin_machine",
        "twitter": _ROOT_DIR / "machines" / "twitter_machine",
    }


class SmartScheduler:
    """Scheduler intelligent qui évite les conflits d'heures."""
    
    def __init__(self):
        self.all_schedules = {}
        self.load_all_schedules()
    
    def load_all_schedules(self):
        """Charge tous les schedules de tous les comptes."""
        for platform, base_path in PLATFORM_BASE.items():
            self.all_schedules[platform] = []
            
            # Charger le schedule par défaut (racine)
            default_schedule = base_path / "schedule.json"
            if default_schedule.exists():
                try:
                    data = json.loads(default_schedule.read_text(encoding="utf-8"))
                    self.all_schedules[platform].append({
                        "account_id": None,
                        "schedule": data.get("schedule", [])
                    })
                except Exception as e:
                    logger.warning(f"Erreur load schedule {platform}: {e}")
            
            # Charger les schedules des accounts (nouvelle structure: accounts/{id}/schedule.json)
            accounts_dir = base_path / "accounts"
            if accounts_dir.exists() and accounts_dir.is_dir():
                for acct in accounts_dir.iterdir():
                    if not acct.is_dir():
                        continue
                    try:
                        account_id = int(acct.name)
                    except Exception:
                        # skip non-numeric directories
                        continue
                    schedule_file = acct / "schedule.json"
                    if schedule_file.exists():
                        try:
                            data = json.loads(schedule_file.read_text(encoding="utf-8"))
                            self.all_schedules[platform].append({
                                "account_id": account_id,
                                "schedule": data.get("schedule", [])
                            })
                        except Exception as e:
                            logger.warning(f"Erreur load schedule {platform}/accounts/{account_id}: {e}")

            # Legacy directories (acc_*) are no longer supported. Only use accounts/<id>/schedule.json
    
    def get_occupied_hours(self, platform: str, exclude_account: int = None) -> List[int]:
        """Retourne les heures occupées pour une plateforme."""
        hours = []
        
        if platform not in self.all_schedules:
            return hours
        
        for sched_info in self.all_schedules[platform]:
            account_id = sched_info.get("account_id")
            if account_id == exclude_account:
                continue
            
            for slot in sched_info.get("schedule", []):
                hour = slot.get("hour")
                if hour is not None:
                    hours.append(hour)
        
        return sorted(set(hours))
    
    def find_free_hour(self, platform: str, preferred_hour: int = 21, 
                      exclude_account: int = None, max_hour: int = 23) -> int:
        """
        Trouve une heure libre pour éviter les conflits.
        
        Args:
            platform: Plateforme cible
            preferred_hour: Heure souhaitée
            exclude_account: ID du compte à exclure (lui-même)
            max_hour: Dernière heure possible
        
        Returns:
            Une heure libre
        """
        occupied = set(self.get_occupied_hours(platform, exclude_account))
        
        # Essayer l'heure préférée
        if preferred_hour not in occupied and preferred_hour <= max_hour:
            return preferred_hour
        
        # Chercher l'heure la plus proche après
        for hour in range(preferred_hour + 1, max_hour + 1):
            if hour not in occupied:
                logger.info(f"[SmartScheduler] Décalage {preferred_hour}h -> {hour}h (conflict)")
                return hour
        
        # Si rien après, chercher avant
        for hour in range(8, preferred_hour):
            if hour not in occupied:
                logger.info(f"[SmartScheduler] Décalage {preferred_hour}h -> {hour}h (after full)")
                return hour
        
        # Retourner l'heure préférée même si occupée (emergency fallback)
        return preferred_hour
    
    def get_conflicts(self, platform: str, hour: int, exclude_account: int = None) -> List[Dict]:
        """Retourne les conflits pour une heure donnée."""
        conflicts = []
        
        if platform not in self.all_schedules:
            return conflicts
        
        for sched_info in self.all_schedules[platform]:
            account_id = sched_info.get("account_id")
            if account_id == exclude_account:
                continue
            
            for slot in sched_info.get("schedule", []):
                if slot.get("hour") == hour:
                    conflicts.append({
                        "account_id": account_id,
                        "persona": slot.get("persona"),
                        "type": slot.get("type")
                    })
        
        return conflicts
    
    def save_schedule(self, platform: str, account_id: int, schedule: List[Dict]) -> bool:
        """Sauvegarde le schedule pour un compte."""
        base = PLATFORM_BASE.get(platform)
        if not base:
            return False
        
        if account_id:
            schedule_file = base / "accounts" / str(account_id) / "schedule.json"
        else:
            schedule_file = base / "schedule.json"
        
        try:
            schedule_file.parent.mkdir(parents=True, exist_ok=True)
            schedule_file.write_text(json.dumps({"schedule": schedule}, ensure_ascii=False, indent=2), encoding="utf-8")
            # Recharger
            self.load_all_schedules()
            return True
        except Exception as e:
            logger.error(f"Erreur save schedule: {e}")
            return False


# === FONCTIONS UTILITAIRES ===

def get_free_hour(platform: str, preferred_hour: int = 21, account_id: int = None) -> int:
    """Trouve une heure libre rapidement."""
    sched = SmartScheduler()
    return sched.find_free_hour(platform, preferred_hour, account_id)


def check_conflicts(platform: str, hour: int, account_id: int = None) -> List[Dict]:
    """Vérifie les conflits."""
    sched = SmartScheduler()
    return sched.get_conflicts(platform, hour, account_id)


if __name__ == "__main__":
    sched = SmartScheduler()
    
    print("=== Occupied Hours ===")
    for p in ["facebook", "linkedin", "twitter"]:
        hours = sched.get_occupied_hours(p)
        print(f"{p}: {hours}")
    
    print("\n=== Test find free hour ===")
    for p in ["facebook", "linkedin", "twitter"]:
        free = sched.find_free_hour(p, 21)
        print(f"{p} suggestions for 21h: {free}")