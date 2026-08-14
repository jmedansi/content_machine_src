"""Platform loader - discovers and loads platform plugins dynamically."""

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Optional

from core.shared.base import PlatformRegistry, PlatformType, BasePlatform


class PlatformLoader:
    """Dynamically loads platform plugins from the platforms directory."""
    
    _loaded: set[str] = set()
    
    @classmethod
    def discover_platforms(cls, platforms_dir: Optional[str] = None) -> list[PlatformType]:
        """Discover available platforms in the platforms directory."""
        if platforms_dir is None:
            platforms_dir = Path(__file__).parent.parent / "platforms"
        
        platforms = []
        for entry in os.listdir(platforms_dir):
            platform_path = platforms_dir / entry
            if platform_path.is_dir() and not entry.startswith("_"):
                try:
                    platform_type = PlatformType(entry.lower())
                    platforms.append(platform_type)
                except ValueError:
                    pass
        
        return platforms
    
    @classmethod
    def load_platform(cls, platform_type: PlatformType, config: dict) -> BasePlatform:
        """Load a platform plugin by type.
        
        Looks for platforms/<platform_type>/__init__.py which should have a 
        register() function that registers the platform class.
        """
        key = platform_type.value
        
        if key in cls._loaded:
            return PlatformRegistry.create(platform_type, config)
        
        platforms_dir = Path(__file__).parent.parent / "platforms"
        platform_dir = platforms_dir / key
        
        if not platform_dir.exists():
            raise FileNotFoundError(f"Platform directory not found: {platform_dir}")
        
        init_file = platform_dir / "__init__.py"
        if not init_file.exists():
            raise FileNotFoundError(f"Platform __init__.py not found: {init_file}")
        
        module_name = f"core.platforms.{key}"
        spec = importlib.util.spec_from_file_location(module_name, init_file)
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
            
            if hasattr(module, "register"):
                module.register()
            
            cls._loaded.add(key)
            
        except Exception as e:
            raise ImportError(f"Failed to load platform {key}: {e}") from e
        
        return PlatformRegistry.create(platform_type, config)
    
    @classmethod
    def load_all(cls, configs: dict[PlatformType, dict]) -> dict[PlatformType, BasePlatform]:
        """Load all configured platforms."""
        platforms = {}
        
        available = cls.discover_platforms()
        
        for platform_type in available:
            if platform_type in configs:
                platforms[platform_type] = cls.load_platform(platform_type, configs[platform_type])
        
        return platforms
    
    @classmethod
    def reload(cls, platform_type: PlatformType) -> None:
        """Reload a platform (useful for development)."""
        key = platform_type.value
        if key in cls._loaded:
            cls._loaded.remove(key)
        PlatformRegistry.clear_instances()