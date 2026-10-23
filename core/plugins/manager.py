import os
import json
import importlib.util
from typing import Dict, Any, List, Optional
from core.logging.logger import logger
from .context import PluginContext
from .registry import PluginRegistry
from .validator import PluginValidator

class PluginManager:
    """
    Plugin discovery, registration, lifecycle, and auto-loader orchestrator.
    """
    def __init__(self, context: PluginContext):
        self.context = context
        self.registry = PluginRegistry()
        self.plugins_directory = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "plugins")
        )

    async def discover_and_load(self) -> None:
        if not os.path.isdir(self.plugins_directory):
            return

        for item in os.listdir(self.plugins_directory):
            plugin_dir = os.path.join(self.plugins_directory, item)
            if not os.path.isdir(plugin_dir):
                continue

            manifest_path = os.path.join(plugin_dir, "plugin.json")
            if not os.path.isfile(manifest_path):
                # Auto-generate minimal manifest
                manifest = {
                    "name": item,
                    "version": "1.0.0",
                    "main": "__init__.py",
                    "description": f"MomentumOne plugin {item}"
                }
            else:
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception as err:
                    logger.error(f"[PluginManager] Could not read manifest in {item}: {err}")
                    continue

            val = PluginValidator.validate(manifest)
            if not val.get("valid"):
                logger.warn(f"[PluginManager] Skipping invalid plugin {item}: {val.get('error')}")
                continue

            main_file = os.path.join(plugin_dir, manifest.get("main", "__init__.py"))
            if not os.path.isfile(main_file):
                logger.error(f"[PluginManager] Main entry file {main_file} not found for {item}")
                continue

            if self.registry.get(item):
                continue

            try:
                import sys
                pkg_name = f"plugins.{item}"
                spec = importlib.util.spec_from_file_location(pkg_name, main_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = pkg_name
                    sys.modules[pkg_name] = mod
                    spec.loader.exec_module(mod)
                    
                    plugin_class = getattr(mod, "Plugin", getattr(mod, item, None))
                    if plugin_class:
                        instance = plugin_class(self.context)
                        self.registry.register(item, manifest, instance)
                        if hasattr(instance, "on_load"):
                            res = instance.on_load()
                            if hasattr(res, "__await__"):
                                await res
                        logger.info(f"[PluginManager] Successfully loaded plugin '{item}'")
            except Exception as err:
                logger.error(f"[PluginManager] Error loading plugin {item}: {err}")

    async def enable(self, plugin_id: str) -> bool:
        record = self.registry.get(plugin_id)
        if not record or record.enabled:
            return False

        if hasattr(record.instance, "on_enable"):
            res = record.instance.on_enable()
            if hasattr(res, "__await__"):
                await res

        record.enabled = True
        logger.info(f"[PluginManager] Enabled plugin '{plugin_id}'")
        return True

    async def enable_all(self) -> None:
        for record in self.registry.list_all():
            if not record.enabled:
                await self.enable(record.plugin_id)

    async def disable(self, plugin_id: str) -> bool:
        record = self.registry.get(plugin_id)
        if not record or not record.enabled:
            return False

        if hasattr(record.instance, "on_disable"):
            res = record.instance.on_disable()
            if hasattr(res, "__await__"):
                await res

        record.enabled = False
        logger.info(f"[PluginManager] Disabled plugin '{plugin_id}'")
        return True
