"""E2E tests for Content Machine - Simple version."""

import asyncio
import asyncio
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _fb_config():
    return {
        "base_dir": str(ROOT / "machines" / "facebook_machine"),
        "page_id": "test",
        "access_token": "test"
    }


def _li_config():
    return {
        "base_dir": str(ROOT / "machines" / "linkedin_machine"),
        "access_token": "test"
    }


async def test_facebook():
    """Test Facebook platform."""
    print("Testing Facebook platform...")
    
    from core.shared.base import PlatformType, ContentType
    from core.shared.loader import PlatformLoader
    
    platform = PlatformLoader.load_platform(PlatformType.FACEBOOK, _fb_config())
    
    assert platform.platform_type == PlatformType.FACEBOOK
    assert ContentType.POST in platform.supported_content_types
    
    personas = platform.get_personas()
    assert len(personas) > 0
    
    print(f"  Facebook: OK ({len(personas)} personas)")
    return True


async def test_linkedin():
    """Test LinkedIn platform."""
    print("Testing LinkedIn platform...")
    
    from core.shared.base import PlatformType, ContentType
    from core.shared.loader import PlatformLoader
    
    platform = PlatformLoader.load_platform(PlatformType.LINKEDIN, _li_config())
    
    assert platform.platform_type == PlatformType.LINKEDIN
    assert ContentType.CAROUSEL in platform.supported_content_types
    
    print("  LinkedIn: OK")
    return True


async def test_orchestrator():
    """Test orchestrator."""
    print("Testing Orchestrator...")
    
    from core.shared.base import PlatformType
    from orchestrator import ContentOrchestrator, OrchestratorConfig
    
    config = OrchestratorConfig(facebook_config=_fb_config())
    
    orch = ContentOrchestrator(config)
    await orch.initialize()
    
    platforms = orch.list_platforms()
    assert PlatformType.FACEBOOK in platforms
    
    fb = orch.get_platform(PlatformType.FACEBOOK)
    personas = fb.get_personas()
    
    print(f"  Orchestrator: OK ({len(platforms)} platforms)")
    return True


async def main():
    print("=" * 50)
    print("Content Machine - E2E Tests")
    print("=" * 50)
    
    tests = [test_facebook, test_linkedin, test_orchestrator]
    
    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    print("=" * 50)
    print("ALL TESTS PASSED")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)