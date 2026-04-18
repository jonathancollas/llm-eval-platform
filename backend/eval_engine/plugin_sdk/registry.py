from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional
import importlib.util, os, logging

logger = logging.getLogger(__name__)

@dataclass
class RegisteredPlugin:
    plugin_class: type; manifest_name: str; plugin_type: str
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

class PluginRegistry:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins: dict[str, RegisteredPlugin] = {}
        return cls._instance

    def register(self, cls, plugin_type: str):
        name = getattr(cls, '__name__', str(cls))
        self._plugins[name] = RegisteredPlugin(plugin_class=cls, manifest_name=name, plugin_type=plugin_type)

    def register_benchmark(self, cls): self.register(cls, "benchmark"); return cls
    def register_metric(self, cls): self.register(cls, "metric"); return cls
    def register_judge(self, cls): self.register(cls, "judge"); return cls
    def register_environment(self, cls): self.register(cls, "environment"); return cls

    def get_benchmark(self, name: str) -> Optional[type]:
        p = self._plugins.get(name)
        return p.plugin_class if p and p.plugin_type == "benchmark" else None

    def get_metric(self, name: str) -> Optional[type]:
        p = self._plugins.get(name)
        return p.plugin_class if p and p.plugin_type == "metric" else None

    def list_plugins(self, plugin_type: Optional[str] = None) -> list:
        return [p for p in self._plugins.values() if plugin_type is None or p.plugin_type == plugin_type]

    def discover_plugins(self, directory: str) -> int:
        count = 0
        if not os.path.isdir(directory): return 0
        for fname in os.listdir(directory):
            if fname.endswith(".py") and not fname.startswith("_"):
                try:
                    spec = importlib.util.spec_from_file_location(fname[:-3], os.path.join(directory, fname))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        count += 1
                except Exception as e:
                    logger.warning(f"Plugin discovery failed for {fname}: {e}")
        return count

plugin_registry = PluginRegistry()

def plugin_benchmark(cls): plugin_registry.register_benchmark(cls); return cls
def plugin_metric(cls): plugin_registry.register_metric(cls); return cls
def plugin_judge(cls): plugin_registry.register_judge(cls); return cls
def plugin_environment(cls): plugin_registry.register_environment(cls); return cls
