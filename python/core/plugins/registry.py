from typing import Dict, Any, List, Optional
from core.logging.logger import logger

class PluginRecord:
    def __init__(self, plugin_id: str, manifest: Dict[str, Any], instance: Any):
        self.plugin_id = plugin_id
        self.manifest = manifest
        self.instance = instance
        self.enabled = False

class PluginRegistry:
    """
    Plugin registration and lifecycle store.
    """
    def __init__(self):
        self._plugins: Dict[str, PluginRecord] = {}

    def register(self, plugin_id: str, manifest: Dict[str, Any], instance: Any) -> Dict[str, Any]:
        logger.info(f"[PluginRegistry] Registering plugin '{manifest.get('name', plugin_id)}' (v{manifest.get('version', '1.0.0')})")
        record = PluginRecord(plugin_id=plugin_id, manifest=manifest, instance=instance)
        self._plugins[plugin_id] = record
        return {
            "success": True,
            "is_registered": True,
            "plugin_id": plugin_id,
        }

    def unregister(self, plugin_id: str) -> Dict[str, Any]:
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            return {"success": True, "is_unregistered": True}
        return {"success": False, "error": "Plugin not found"}

    def get(self, plugin_id: str) -> Optional[PluginRecord]:
        return self._plugins.get(plugin_id)

    def list_all(self) -> List[PluginRecord]:
        return list(self._plugins.values())

    def list_manifests(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": p.plugin_id,
                "name": p.manifest.get("name", p.plugin_id),
                "version": p.manifest.get("version", "1.0.0"),
                "description": p.manifest.get("description", ""),
                "enabled": p.enabled,
            }
            for p in self._plugins.values()
        ]
